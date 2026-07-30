import logging

from django.urls import reverse

from communications.models import OutboundMessage
from communications.services import enqueue_message
from sites.models import SiteRole

from .models import Notification

logger = logging.getLogger(__name__)


def notify_site_staff(
    *, site, kind, title, message, action_url="", dedupe_key="", email=True
):
    roles = (
        SiteRole.objects.filter(site=site, is_active=True)
        .select_related("user")
        .order_by("user_id")
    )
    created = []
    for role in roles:
        values = {
            "site": site,
            "kind": kind,
            "title": title,
            "message": message,
            "action_url": action_url,
        }
        if dedupe_key:
            notification, was_created = Notification.objects.get_or_create(
                recipient=role.user,
                dedupe_key=dedupe_key,
                defaults=values,
            )
        else:
            notification = Notification.objects.create(
                recipient=role.user,
                dedupe_key="",
                **values,
            )
            was_created = True
        if was_created:
            created.append(notification)
            if email and role.user.email:
                enqueue_message(
                    site=site,
                    kind=OutboundMessage.Kind.EVENT_UPDATE,
                    recipient_email=role.user.email,
                    subject=f"{site.display_name}: {title}",
                    body=f"{message}\n\nOpen Gather HQs: {action_url}"
                    if action_url
                    else message,
                    dedupe_key=(
                        f"staff-notification:{notification.id}"
                        if notification.id
                        else ""
                    ),
                )
    return created


def notify_registration_response(registration, history):
    occurrence = registration.occurrence
    contact_name = registration.contact.display_name or registration.contact.email
    response = registration.get_response_display()
    guest_count = history.guest_count
    guest_text = (
        f" with {guest_count} guest{'s' if guest_count != 1 else ''}"
        if guest_count
        else ""
    )
    title = f"New response: {occurrence.event.title}"
    message = (
        f"{contact_name} responded {response}{guest_text} for {occurrence.event.title}."
    )
    action_url = reverse(
        "attendance:roster",
        kwargs={"site_id": registration.site_id, "occurrence_id": occurrence.id},
    )
    return notify_site_staff(
        site=registration.site,
        kind=Notification.Kind.RSVP,
        title=title,
        message=message,
        action_url=action_url,
        dedupe_key=f"registration-response:{history.id}",
        email=True,
    )
