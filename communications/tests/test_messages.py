from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone

from communications.models import OutboundMessage
from communications.services import deliver_message, enqueue_message
from contacts.models import ConsentStatus, Contact
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
        html_body="<p><strong>The time changed.</strong></p>",
    )

    deliver_message(message.id)
    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SENT
    assert message.body == ""
    assert message.html_body == ""
    assert len(mail.outbox) == 1
    assert mail.outbox[0].alternatives[0].mimetype == "text/html"
    assert (
        "<strong>The time changed.</strong>" in mail.outbox[0].alternatives[0].content
    )


@pytest.mark.django_db
def test_redelivered_task_does_not_resend_a_message_still_marked_processing():
    _, site, _ = reminder_fixture()
    message = enqueue_message(
        site=site,
        kind=OutboundMessage.Kind.EVENT_UPDATE,
        recipient_email="alex@example.com",
        subject="Updated event",
        body="The time changed.",
        html_body="<p><strong>The time changed.</strong></p>",
        dispatch=False,
    )
    # Simulate a worker that claimed the message (CELERY_TASK_ACKS_LATE) and
    # was killed mid-send, before writing SENT/FAILED back. The broker
    # redelivers the same task, so deliver_message runs again while status is
    # still PROCESSING from the interrupted attempt.
    message.status = OutboundMessage.Status.PROCESSING
    message.attempts = 1
    message.save(update_fields=("status", "attempts", "updated_at"))

    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.PROCESSING
    assert message.attempts == 1
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_transactional_message_is_suppressed_for_a_hard_bounced_contact():
    _, site, registration = reminder_fixture()
    registration.contact.email_consent_status = ConsentStatus.SUPPRESSED
    registration.contact.save(update_fields=("email_consent_status", "updated_at"))
    message = enqueue_message(
        site=site,
        kind=OutboundMessage.Kind.REMINDER,
        recipient_email=registration.contact.email,
        subject="Reminder",
        body="See you soon.",
        contact=registration.contact,
        registration=registration,
        dispatch=False,
    )

    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SUPPRESSED
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_transactional_message_is_suppressed_for_an_archived_contact():
    _, site, registration = reminder_fixture()
    registration.contact.archived_at = timezone.now()
    registration.contact.save(update_fields=("archived_at", "updated_at"))
    message = enqueue_message(
        site=site,
        kind=OutboundMessage.Kind.INVITATION,
        recipient_email=registration.contact.email,
        subject="Invitation",
        body="Join us.",
        contact=registration.contact,
        dispatch=False,
    )

    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SUPPRESSED
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_transactional_message_does_not_require_marketing_consent():
    _, site, registration = reminder_fixture()
    assert registration.contact.email_consent_status == ConsentStatus.UNKNOWN

    message = enqueue_message(
        site=site,
        kind=OutboundMessage.Kind.CONFIRMATION,
        recipient_email=registration.contact.email,
        subject="RSVP",
        body="You're going!",
        contact=registration.contact,
        registration=registration,
        dispatch=False,
    )

    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SENT
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
    assert "almost time!" in message.html_body
    assert "Friday dance" in message.html_body
