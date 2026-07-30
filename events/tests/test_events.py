from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from contacts.models import Contact
from events.models import Event, EventOccurrence
from events.services import (
    create_event_series,
    occurrence_starts,
    update_occurrences_from,
)
from sites.services import create_subscriber_site
from users.models import User


def create_site(slug="boot-scooters"):
    owner = User.objects.create_user(
        email=f"{slug}@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug=slug,
        timezone_name="America/New_York",
    )
    return owner, site


def create_series(site, owner, *, visibility=Event.Visibility.PUBLIC, slug="lessons"):
    first_start = datetime(2026, 8, 3, 18, 0, tzinfo=ZoneInfo(site.timezone))
    return create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": f"{visibility.title()} lessons",
            "slug": slug,
            "description": "Weekly country line dancing.",
            "host_name": "Pat",
            "visibility": visibility,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.WEEKLY,
            "recurrence_interval": 1,
            "recurrence_until": first_start.date() + timedelta(weeks=2),
        },
        first_start=first_start,
        first_end=first_start + timedelta(hours=2),
        venue_name="Town Hall",
        capacity=40,
    )


@pytest.mark.django_db
def test_event_manager_filters_without_per_occurrence_metric_queries(client):
    owner, site = create_site()
    event = Event.objects.create(
        site=site,
        created_by=owner,
        title="Welcome dance",
        slug="welcome-dance",
        status=Event.Status.PUBLISHED,
    )
    Event.objects.create(
        site=site,
        created_by=owner,
        title="Archived dance",
        slug="archived-dance",
        status=Event.Status.ARCHIVED,
    )
    starts_at = timezone.now() + timedelta(days=1)
    EventOccurrence.objects.bulk_create(
        [
            EventOccurrence(
                site=site,
                event=event,
                starts_at=starts_at + timedelta(days=number),
                ends_at=starts_at + timedelta(days=number, hours=2),
                timezone=site.timezone,
                capacity=50,
            )
            for number in range(10)
        ]
    )
    client.force_login(owner)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("events:manage", args=(site.id,)))
    filtered = client.get(
        reverse("events:manage", args=(site.id,)),
        {"q": "Welcome", "status": "published"},
    )

    assert response.status_code == filtered.status_code == 200
    assert len(queries) < 20
    assert "Welcome dance" in filtered.content.decode()
    assert "Archived dance" not in filtered.content.decode()


@pytest.mark.django_db
def test_weekly_series_materializes_occurrences_in_site_timezone():
    owner, site = create_site()
    event = create_series(site, owner)

    occurrences = list(event.occurrences.all())
    assert len(occurrences) == 3
    assert all(item.timezone == "America/New_York" for item in occurrences)
    assert occurrences[1].starts_at - occurrences[0].starts_at == timedelta(weeks=1)


def test_monthly_recurrence_keeps_the_original_day_after_a_short_month():
    first = datetime(2027, 1, 31, 18, 0, tzinfo=ZoneInfo("America/New_York"))

    starts = list(
        occurrence_starts(
            first,
            Event.Recurrence.MONTHLY,
            1,
            datetime(2027, 3, 31).date(),
        )
    )

    assert [item.day for item in starts] == [31, 28, 31]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("scope", "shifted_indexes"),
    (("one", {1}), ("future", {1, 2}), ("all", {0, 1, 2})),
)
def test_occurrence_edit_scopes_change_the_expected_dates(scope, shifted_indexes):
    owner, site = create_site()
    event = create_series(site, owner)
    before = list(event.occurrences.values_list("starts_at", flat=True))
    target = event.occurrences.all()[1]

    update_occurrences_from(
        occurrence=target,
        scope=scope,
        values={
            "starts_at": target.starts_at + timedelta(hours=1),
            "ends_at": target.ends_at + timedelta(hours=1),
            "venue_name": "New Hall",
            "venue_address": "100 Main Street",
            "capacity": 50,
            "status": EventOccurrence.Status.SCHEDULED,
        },
    )

    after = list(event.occurrences.values_list("starts_at", flat=True))
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        expected = old + timedelta(hours=1) if index in shifted_indexes else old
        assert new == expected


@pytest.mark.django_db
def test_calendar_lists_public_events_but_direct_unlisted_links_work(client):
    owner, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    public = create_series(site, owner, slug="public-lessons")
    unlisted = create_series(
        site, owner, visibility=Event.Visibility.UNLISTED, slug="unlisted-lessons"
    )
    invite_only = create_series(
        site, owner, visibility=Event.Visibility.INVITE_ONLY, slug="private-lessons"
    )
    host = {"host": "boot-scooters.localhost"}

    calendar_response = client.get(reverse("events:calendar"), headers=host)
    unlisted_response = client.get(
        reverse("events:detail", kwargs={"slug": unlisted.slug}), headers=host
    )
    private_response = client.get(
        reverse("events:detail", kwargs={"slug": invite_only.slug}), headers=host
    )

    calendar_content = calendar_response.content.decode()
    assert public.title in calendar_content
    assert unlisted.title not in calendar_content
    assert invite_only.title not in calendar_content
    assert unlisted_response.status_code == 200
    assert private_response.status_code == 404


@pytest.mark.django_db
def test_event_editor_guides_owner_through_access_and_recurrence(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.get(reverse("events:create", args=(site.id,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "data-event-editor" in content
    assert "Who can attend?" in content
    assert "Does it repeat?" in content
    assert "Create event and continue" in content
    assert response.context["form"].initial["host_name"] == site.display_name


@pytest.mark.django_db
def test_new_event_redirects_to_highlighted_next_actions(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.post(
        reverse("events:create", args=(site.id,)),
        {
            "title": "Friday Night Line Dance",
            "slug": "friday-night-line-dance",
            "description": "A friendly social dance for all levels.",
            "host_name": site.display_name,
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": "",
            "max_guests": 2,
            "start_date": "2026-09-18",
            "start_time": "19:00",
            "end_date": "2026-09-18",
            "end_time": "21:00",
            "venue_name": "Town Hall",
            "venue_address": "100 Main Street",
            "capacity": 60,
        },
    )

    event = Event.objects.get(slug="friday-night-line-dance")
    assert response.status_code == 302
    assert response.url.endswith(f"?created={event.id}")

    followup = client.get(response.url)
    content = followup.content.decode()
    assert "What would you like to do next?" in content
    assert "Invite contacts" in content
    assert "Add tickets" in content
    assert "Friday Night Line Dance" in content


@pytest.mark.django_db
def test_invitation_picker_shows_contact_email_and_search_controls(client):
    owner, site = create_site()
    event = create_series(site, owner)
    occurrence = event.occurrences.first()
    Contact.objects.create(
        site=site,
        first_name="Pat",
        last_name="Dancer",
        email="pat@example.com",
    )
    client.force_login(owner)

    response = client.get(reverse("events:invite", args=(site.id, occurrence.id)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "data-invite-picker" in content
    assert "Pat Dancer - pat@example.com" in content
    assert "Search by name or email" in content
    assert "Personal invitation links" in content
