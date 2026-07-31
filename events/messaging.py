from datetime import timedelta
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from communications.models import OutboundMessage
from communications.services import enqueue_message

from .models import Event, EventOccurrence, Participant, Registration


def _when(occurrence):
    local_start = occurrence.starts_at.astimezone(ZoneInfo(occurrence.timezone))
    hour = local_start.hour % 12 or 12
    return (
        f"{local_start.strftime('%A, %B')} {local_start.day} at "
        f"{hour}:{local_start.strftime('%M %p')}"
    )


def _participant_names(registration):
    names = registration.participants.filter(
        status=Participant.Status.ACTIVE
    ).values_list("first_name", "last_name")
    return [f"{first} {last}".strip() for first, last in names]


def _participant_lines(participant_names):
    return "\n".join(f"- {name}" for name in participant_names)


def _canonical_hostname(site):
    return site.domains.get(is_canonical=True).hostname


def _brand_asset_url(site, hostname, asset):
    theme = getattr(site, "theme", None)
    brand_file = None
    if theme is not None:
        brand_file = theme.logo if asset == "logo" else theme.hero_image
    if not brand_file:
        return ""
    version = int(theme.updated_at.timestamp())
    path = reverse("content:public_brand_asset", kwargs={"asset": asset})
    return f"https://{hostname}{path}?v={version}"


def _public_event_url(occurrence, hostname):
    if (
        occurrence.event.status != Event.Status.PUBLISHED
        or occurrence.event.visibility == Event.Visibility.INVITE_ONLY
        or occurrence.status != EventOccurrence.Status.SCHEDULED
    ):
        return ""
    path = reverse(
        "events:occurrence_detail",
        kwargs={
            "slug": occurrence.event.slug,
            "occurrence_id": occurrence.id,
        },
    )
    return f"https://{hostname}{path}"


def _description(occurrence):
    event_description = occurrence.event.description.strip()
    if event_description:
        return event_description
    theme = getattr(occurrence.site, "theme", None)
    return theme.hero_text.strip() if theme is not None else ""


def _plain_event_details(occurrence):
    lines = [
        f"When: {_when(occurrence)}",
        f"Where: {occurrence.venue_name or 'Details to be announced'}",
    ]
    if occurrence.venue_address:
        lines.append(f"Address: {occurrence.venue_address}")
    host = occurrence.event.host_name or occurrence.site.display_name
    lines.append(f"Hosted by: {host}")
    return "\n".join(lines)


def _event_email_html(
    *,
    occurrence,
    hostname,
    subject,
    preheader,
    eyebrow,
    headline,
    status_label="",
    status_value="",
    participants=None,
    note="",
    primary_url="",
    primary_label="",
    secondary_url="",
    secondary_label="",
):
    site = occurrence.site
    theme = getattr(site, "theme", None)
    return render_to_string(
        "events/email/event_message.html",
        {
            "subject": subject,
            "preheader": preheader,
            "site_name": site.display_name,
            "primary_color": theme.primary_color if theme else "#0B1D39",
            "secondary_color": theme.secondary_color if theme else "#516543",
            "logo_url": _brand_asset_url(site, hostname, "logo"),
            "hero_url": _brand_asset_url(site, hostname, "hero"),
            "eyebrow": eyebrow,
            "headline": headline,
            "event_title": occurrence.event.title,
            "description": _description(occurrence),
            "when": _when(occurrence),
            "venue": occurrence.venue_name or "Details to be announced",
            "address": occurrence.venue_address,
            "host": occurrence.event.host_name or site.display_name,
            "status_label": status_label,
            "status_value": status_value,
            "participants": participants or [],
            "note": note,
            "primary_url": primary_url,
            "primary_label": primary_label,
            "secondary_url": secondary_url,
            "secondary_label": secondary_label,
        },
    )


def queue_invitation(*, invitation, token, response_url):
    occurrence = invitation.occurrence
    hostname = _canonical_hostname(invitation.site)
    subject = f"You're invited: {occurrence.event.title}"
    description = _description(occurrence)
    description_block = f"{description}\n\n" if description else ""
    body = (
        f"Hi {invitation.contact.first_name or 'there'},\n\n"
        f"You're invited to {occurrence.event.title}.\n\n"
        f"{description_block}{_plain_event_details(occurrence)}\n\n"
        f"Choose Going, Maybe, or Not going: {response_url}"
    )
    html_body = _event_email_html(
        occurrence=occurrence,
        hostname=hostname,
        subject=subject,
        preheader=f"Join us for {occurrence.event.title} on {_when(occurrence)}.",
        eyebrow="You're invited",
        headline=(
            f"We'd love to see you, {invitation.contact.first_name}!"
            if invitation.contact.first_name
            else "We'd love to see you!"
        ),
        note="No account is required. Let the host know if you're going, maybe, or unable to attend.",
        primary_url=response_url,
        primary_label="View invitation and RSVP",
    )
    return enqueue_message(
        site=invitation.site,
        kind=OutboundMessage.Kind.INVITATION,
        recipient_email=invitation.contact.email,
        subject=subject,
        body=body,
        html_body=html_body,
        dedupe_key=f"invitation:{invitation.id}:{invitation.token_hash[:16]}",
        occurrence=occurrence,
        invitation=invitation,
    )


def queue_confirmation(registration, history):
    if not registration.contact.email:
        return None
    occurrence = registration.occurrence
    hostname = _canonical_hostname(registration.site)
    participant_names = _participant_names(registration)
    participant_lines = _participant_lines(participant_names)
    participants = (
        f"\nYour party:\n{participant_lines}\n" if participant_lines else ""
    )
    manage_url = ""
    if registration.source == Registration.Source.PUBLIC:
        from events.registration import public_rsvp_manage_token

        manage_path = reverse(
            "events:public_response_manage",
            kwargs={
                "slug": occurrence.event.slug,
                "occurrence_id": registration.occurrence_id,
                "token": public_rsvp_manage_token(registration),
            },
        )
        manage_url = f"https://{hostname}{manage_path}"

    payment_url = ""
    if registration.payment_status == Registration.PaymentStatus.PENDING:
        from payments.services import registration_checkout_token

        checkout_path = reverse(
            "payments:ticket_checkout",
            kwargs={"token": registration_checkout_token(registration)},
        )
        payment_url = f"https://{hostname}{checkout_path}"
        payment_text = (
            "Payment is required before your spots are confirmed. "
            "Complete checkout within 30 minutes."
        )
        payment_line = f"Payment: Required\nPay within 30 minutes: {payment_url}"
    else:
        payment_text = "No payment is required for this event."
        payment_line = "Payment: Free event."

    manage_line = f"\n\nManage your response: {manage_url}" if manage_url else ""
    subject = f"RSVP: {occurrence.event.title}"
    body = (
        f"Your response is {registration.get_response_display()} for "
        f"{occurrence.event.title}.\n\n{_plain_event_details(occurrence)}"
        f"{participants}\n{payment_line}{manage_line}"
    )
    event_url = _public_event_url(occurrence, hostname)
    primary_url = payment_url or manage_url or event_url
    primary_label = (
        "Choose tickets and pay"
        if payment_url
        else "Manage your response"
        if manage_url
        else "View event details"
        if event_url
        else ""
    )
    html_body = _event_email_html(
        occurrence=occurrence,
        hostname=hostname,
        subject=subject,
        preheader=(
            f"You're marked {registration.get_response_display().lower()} for "
            f"{occurrence.event.title}."
        ),
        eyebrow="Response saved",
        headline=f"You're {registration.get_response_display().lower()}!",
        status_label="Your response",
        status_value=registration.get_response_display(),
        participants=participant_names,
        note=payment_text,
        primary_url=primary_url,
        primary_label=primary_label,
        secondary_url=manage_url if payment_url and manage_url else "",
        secondary_label="Manage your response",
    )
    return enqueue_message(
        site=registration.site,
        kind=OutboundMessage.Kind.CONFIRMATION,
        recipient_email=registration.contact.email,
        subject=subject,
        body=body,
        html_body=html_body,
        dedupe_key=f"confirmation:{history.id}",
        occurrence=occurrence,
        registration=registration,
    )


def queue_rsvp_manage_link(registration, *, now=None):
    from events.registration import public_rsvp_manage_token

    now = now or timezone.now()
    occurrence = registration.occurrence
    hostname = _canonical_hostname(registration.site)
    manage_path = reverse(
        "events:public_response_manage",
        kwargs={
            "slug": occurrence.event.slug,
            "occurrence_id": registration.occurrence_id,
            "token": public_rsvp_manage_token(registration),
        },
    )
    manage_url = f"https://{hostname}{manage_path}"
    subject = f"Manage your RSVP: {occurrence.event.title}"
    body = (
        "A request was made to manage your existing RSVP. No account is "
        "required. Use this secure link:\n\n"
        f"{manage_url}\n\n"
        "If you did not make this request, you can ignore this email."
    )
    html_body = _event_email_html(
        occurrence=occurrence,
        hostname=hostname,
        subject=subject,
        preheader=f"Your secure RSVP link for {occurrence.event.title}.",
        eyebrow="Your RSVP",
        headline="Review or change your response",
        note="No account or sign-in is required. If you did not request this link, you can ignore this email.",
        primary_url=manage_url,
        primary_label="Manage your response",
    )
    return enqueue_message(
        site=registration.site,
        kind=OutboundMessage.Kind.CONFIRMATION,
        recipient_email=registration.contact.email,
        subject=subject,
        body=body,
        html_body=html_body,
        dedupe_key=(
            f"rsvp-manage:{registration.id}:{now.strftime('%Y%m%d%H')}"
        ),
        occurrence=occurrence,
        registration=registration,
    )


def queue_occurrence_notice(occurrence, *, cancellation=False, revision_key=None):
    kind = (
        OutboundMessage.Kind.CANCELLATION
        if cancellation
        else OutboundMessage.Kind.EVENT_UPDATE
    )
    label = "Canceled" if cancellation else "Updated"
    hostname = _canonical_hostname(occurrence.site)
    event_url = "" if cancellation else _public_event_url(occurrence, hostname)
    subject = f"{label}: {occurrence.event.title}"
    body = (
        f"{occurrence.event.title} on {_when(occurrence)} has been "
        f"{label.lower()}.\n\n{_plain_event_details(occurrence)}"
    )
    html_body = _event_email_html(
        occurrence=occurrence,
        hostname=hostname,
        subject=subject,
        preheader=f"{occurrence.event.title} has been {label.lower()}.",
        eyebrow="Event notice",
        headline=(
            "This event has been canceled"
            if cancellation
            else "The event details have changed"
        ),
        status_label="Current status",
        status_value=label,
        note=(
            "Please update your plans. Contact the host if you have questions."
            if cancellation
            else "Review the current date, time, and location before you go."
        ),
        primary_url=event_url,
        primary_label="View updated event",
    )
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
            subject=subject,
            body=body,
            html_body=html_body,
            dedupe_key=(
                f"{kind}:{registration.id}:"
                f"{revision_key or occurrence.updated_at.isoformat()}"
            ),
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
        .select_related("site", "site__theme", "contact", "occurrence__event")
        .prefetch_related("participants")
    )
    count = 0
    for registration in registrations:
        if not registration.contact.email:
            continue
        occurrence = registration.occurrence
        hostname = _canonical_hostname(registration.site)
        participant_names = _participant_names(registration)
        participant_lines = _participant_lines(participant_names)
        payment_status = (
            "Paid"
            if registration.payment_status == Registration.PaymentStatus.PAID
            else "Free event"
        )
        subject = f"Reminder: {occurrence.event.title}"
        body = (
            f"Reminder: {occurrence.event.title} is {_when(occurrence)}.\n\n"
            f"{_plain_event_details(occurrence)}\n\nYour party:\n"
            f"{participant_lines}\n\nPayment: {payment_status}."
        )
        event_url = _public_event_url(occurrence, hostname)
        html_body = _event_email_html(
            occurrence=occurrence,
            hostname=hostname,
            subject=subject,
            preheader=f"{occurrence.event.title} is {_when(occurrence)}.",
            eyebrow="Coming up soon",
            headline="It's almost time!",
            status_label="Payment",
            status_value=payment_status,
            participants=participant_names,
            note="Check the time and location, then get ready to enjoy the event.",
            primary_url=event_url,
            primary_label="View event details",
        )
        _, created = OutboundMessage.objects.get_or_create(
            site=registration.site,
            dedupe_key=(
                f"reminder:{registration.id}:"
                f"{occurrence.starts_at.isoformat()}"
            ),
            defaults={
                "kind": OutboundMessage.Kind.REMINDER,
                "recipient_email": registration.contact.email,
                "subject": subject,
                "body": body,
                "html_body": html_body,
                "occurrence": occurrence,
                "registration": registration,
            },
        )
        count += int(created)
    return count
