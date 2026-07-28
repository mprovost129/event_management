from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from communications.models import OutboundMessage
from communications.services import enqueue_message

from .models import Participant, Registration


def _when(occurrence):
    local_start = occurrence.starts_at.astimezone(ZoneInfo(occurrence.timezone))
    hour = local_start.hour % 12 or 12
    return (
        f"{local_start.strftime('%A, %B')} {local_start.day} at "
        f"{hour}:{local_start.strftime('%M %p')}"
    )


def _participant_lines(registration):
    names = registration.participants.filter(
        status=Participant.Status.ACTIVE
    ).values_list("first_name", "last_name")
    return "\n".join(f"- {first} {last}".strip() for first, last in names)


def queue_invitation(*, invitation, token, response_url):
    occurrence = invitation.occurrence
    return enqueue_message(
        site=invitation.site,
        kind=OutboundMessage.Kind.INVITATION,
        recipient_email=invitation.contact.email,
        subject=f"You're invited: {occurrence.event.title}",
        body=(
            f"Hi {invitation.contact.first_name or 'there'},\n\n"
            f"You're invited to {occurrence.event.title} on {_when(occurrence)}.\n"
            f"Respond here: {response_url}\n\n"
            f"Hosted by {occurrence.event.host_name or occurrence.site.display_name}."
        ),
        dedupe_key=f"invitation:{invitation.id}:{invitation.token_hash[:16]}",
        occurrence=occurrence,
        invitation=invitation,
    )


def queue_confirmation(registration, history):
    if not registration.contact.email:
        return None
    participant_lines = _participant_lines(registration)
    participants = (
        f"\nParticipants:\n{participant_lines}\n" if participant_lines else ""
    )
    if registration.payment_status == Registration.PaymentStatus.PENDING:
        from django.urls import reverse

        from payments.services import registration_checkout_token

        hostname = registration.site.domains.get(is_canonical=True).hostname
        checkout_path = reverse(
            "payments:ticket_checkout",
            kwargs={"token": registration_checkout_token(registration)},
        )
        payment_line = (
            "Payment: Required before participants are confirmed.\n"
            f"Pay within 30 minutes: https://{hostname}{checkout_path}"
        )
    else:
        payment_line = "Payment: Free event."
    return enqueue_message(
        site=registration.site,
        kind=OutboundMessage.Kind.CONFIRMATION,
        recipient_email=registration.contact.email,
        subject=f"RSVP: {registration.occurrence.event.title}",
        body=(
            f"Your response is {registration.get_response_display()} for "
            f"{registration.occurrence.event.title} on {_when(registration.occurrence)}."
            f"{participants}\n{payment_line}"
        ),
        dedupe_key=f"confirmation:{history.id}",
        occurrence=registration.occurrence,
        registration=registration,
    )


def queue_occurrence_notice(occurrence, *, cancellation=False, revision_key=None):
    kind = (
        OutboundMessage.Kind.CANCELLATION
        if cancellation
        else OutboundMessage.Kind.EVENT_UPDATE
    )
    label = "Canceled" if cancellation else "Updated"
    count = 0
    registrations = occurrence.registrations.exclude(
        response=Registration.Response.NOT_GOING
    ).select_related("contact", "occurrence__event")
    for registration in registrations:
        if not registration.contact.email:
            continue
        enqueue_message(
            site=occurrence.site,
            kind=kind,
            recipient_email=registration.contact.email,
            subject=f"{label}: {occurrence.event.title}",
            body=(
                f"{occurrence.event.title} on {_when(occurrence)} has been "
                f"{label.lower()}.\n\nVenue: {occurrence.venue_name or 'To be announced'}"
            ),
            dedupe_key=f"{kind}:{registration.id}:{revision_key or occurrence.updated_at.isoformat()}",
            occurrence=occurrence,
            registration=registration,
        )
        count += 1
    return count


def queue_due_reminders(*, now=None):
    now = now or timezone.now()
    starts_after = now + timedelta(hours=23)
    starts_before = now + timedelta(hours=25)
    registrations = (
        Registration.objects.filter(
            response=Registration.Response.GOING,
            payment_status__in=(
                Registration.PaymentStatus.NOT_REQUIRED,
                Registration.PaymentStatus.PAID,
            ),
            occurrence__starts_at__gte=starts_after,
            occurrence__starts_at__lt=starts_before,
        )
        .select_related("site", "contact", "occurrence__event")
        .prefetch_related("participants")
    )
    count = 0
    for registration in registrations:
        if not registration.contact.email:
            continue
        participant_lines = _participant_lines(registration)
        _, created = OutboundMessage.objects.get_or_create(
            site=registration.site,
            dedupe_key=f"reminder:{registration.id}:{registration.occurrence.starts_at.isoformat()}",
            defaults={
                "kind": OutboundMessage.Kind.REMINDER,
                "recipient_email": registration.contact.email,
                "subject": f"Reminder: {registration.occurrence.event.title}",
                "body": (
                    f"Reminder: {registration.occurrence.event.title} is "
                    f"{_when(registration.occurrence)}.\n\nParticipants:\n"
                    f"{participant_lines}\n\nPayment: "
                    f"{'Paid' if registration.payment_status == Registration.PaymentStatus.PAID else 'Free event'}."
                ),
                "occurrence": registration.occurrence,
                "registration": registration,
            },
        )
        count += int(created)
    return count
