from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

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
