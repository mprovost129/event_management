from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone

from communications.models import OutboundMessage
from communications.services import deliver_message, enqueue_message
from contacts.models import Contact
from events.messaging import queue_due_reminders
from events.models import Event, Registration
from events.registration import save_response
from events.services import create_event_series
from sites.services import create_subscriber_site
from users.models import User


def reminder_fixture():
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
    now = timezone.now()
    start = (now + timedelta(hours=24)).astimezone(ZoneInfo(site.timezone))
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
            "max_guests": 0,
        },
        first_start=start,
        first_end=start + timedelta(hours=2),
    )
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    registration, _ = save_response(
        occurrence=event.occurrences.get(),
        contact=contact,
        response=Registration.Response.GOING,
        guests=[],
        source=Registration.Source.MANAGER,
    )
    return now, site, registration


@pytest.mark.django_db
def test_outbound_delivery_is_idempotent():
    _, site, _ = reminder_fixture()
    message = enqueue_message(
        site=site,
        kind=OutboundMessage.Kind.EVENT_UPDATE,
        recipient_email="alex@example.com",
        subject="Updated event",
        body="The time changed.",
    )

    deliver_message(message.id)
    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SENT
    assert message.body == ""
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_outbound_service_rejects_cross_tenant_relationships():
    _, site, _ = reminder_fixture()
    other_owner = User.objects.create_user(
        email="other@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    other_site = create_subscriber_site(
        owner=other_owner,
        display_name="Other Site",
        slug="other-site",
        timezone_name="America/New_York",
    )
    foreign_contact = Contact.objects.create(
        site=other_site,
        first_name="Foreign",
        last_name="Contact",
        email="foreign@example.com",
    )

    with pytest.raises(ValidationError, match="contact must belong"):
        enqueue_message(
            site=site,
            contact=foreign_contact,
            kind=OutboundMessage.Kind.EVENT_UPDATE,
            recipient_email=foreign_contact.email,
            subject="Wrong tenant",
            body="This must not be created.",
        )

    assert not OutboundMessage.objects.filter(subject="Wrong tenant").exists()


@pytest.mark.django_db
def test_due_reminders_are_queued_once():
    now, _, registration = reminder_fixture()

    first = queue_due_reminders(now=now)
    second = queue_due_reminders(now=now)

    assert first == 1
    assert second == 0
    message = OutboundMessage.objects.get(kind=OutboundMessage.Kind.REMINDER)
    assert message.registration == registration
    assert "Alex Dancer" in message.body
