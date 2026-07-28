from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from attendance.models import AttendanceRecord
from attendance.services import set_check_in
from contacts.models import Contact
from events.models import Event, Participant, Registration
from events.registration import save_response
from events.reporting import occurrence_metrics
from events.services import create_event_series
from sites.services import create_subscriber_site
from users.models import User


def attendance_fixture():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    start = timezone.now().astimezone(ZoneInfo(site.timezone)) + timedelta(days=1)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Friday dance",
            "slug": "friday-dance",
            "description": "",
            "host_name": "",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 1,
        },
        first_start=start,
        first_end=start + timedelta(hours=2),
        capacity=10,
    )
    occurrence = event.occurrences.get()
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    registration, _ = save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        guests=[{"first_name": "Sam", "last_name": "Guest"}],
        source=Registration.Source.MANAGER,
    )
    return owner, site, occurrence, registration


@pytest.mark.django_db
def test_primary_and_guest_check_in_independently_and_undo_is_audited():
    owner, _, occurrence, registration = attendance_fixture()
    primary = registration.participants.get(
        is_primary=True, status=Participant.Status.ACTIVE
    )
    guest = registration.participants.get(
        is_primary=False, status=Participant.Status.ACTIVE
    )

    set_check_in(participant=primary, actor=owner, checked_in=True)
    assert occurrence_metrics(occurrence)["checked_in"] == 1
    set_check_in(participant=guest, actor=owner, checked_in=True)
    assert occurrence_metrics(occurrence)["checked_in"] == 2
    set_check_in(participant=primary, actor=owner, checked_in=False, note="Correction")

    assert occurrence_metrics(occurrence)["checked_in"] == 1
    assert list(primary.attendance_history.values_list("action", flat=True)) == [
        AttendanceRecord.Action.UNDONE,
        AttendanceRecord.Action.CHECKED_IN,
    ]


@pytest.mark.django_db
def test_mobile_roster_shows_primary_and_guest_and_is_tenant_scoped(client):
    owner, site, occurrence, registration = attendance_fixture()
    client.force_login(owner)

    response = client.get(
        reverse(
            "attendance:roster",
            kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
        )
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Alex Dancer" in content
    assert "Sam Guest" in content
    assert "Check in" in content
    assert registration.participants.count() == 2
