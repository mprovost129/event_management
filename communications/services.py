import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import OutboundMessage

logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 5


def _dispatch_after_commit(message_id):
    try:
        from .tasks import deliver_outbound_message

        deliver_outbound_message.delay(str(message_id))
    except Exception:
        logger.exception("Unable to dispatch queued outbound message %s", message_id)


def enqueue_message(
    *,
    site,
    kind,
    recipient_email,
    subject,
    body,
    dedupe_key="",
    occurrence=None,
    registration=None,
    invitation=None,
):
    values = {
        "kind": kind,
        "recipient_email": recipient_email,
        "subject": subject,
        "body": body,
        "occurrence": occurrence,
        "registration": registration,
        "invitation": invitation,
    }
    if dedupe_key:
        message, created = OutboundMessage.objects.get_or_create(
            site=site, dedupe_key=dedupe_key, defaults=values
        )
    else:
        message = OutboundMessage.objects.create(site=site, **values)
        created = True
    if created:
        transaction.on_commit(lambda: _dispatch_after_commit(message.id))
    return message


def deliver_message(message_id):
    with transaction.atomic():
        message = OutboundMessage.objects.select_for_update().get(pk=message_id)
        if message.status == OutboundMessage.Status.SENT:
            return message
        if message.attempts >= MAX_DELIVERY_ATTEMPTS:
            return message
        if message.available_at > timezone.now():
            return message
        message.status = OutboundMessage.Status.PROCESSING
        message.attempts += 1
        message.save(update_fields=("status", "attempts", "updated_at"))

    try:
        send_mail(
            subject=message.subject,
            message=message.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[message.recipient_email],
            fail_silently=False,
        )
    except Exception as exc:
        message.status = OutboundMessage.Status.FAILED
        message.last_error = str(exc)[:1000]
        message.available_at = timezone.now() + timedelta(
            minutes=min(60, 2**message.attempts)
        )
        message.save(
            update_fields=("status", "last_error", "available_at", "updated_at")
        )
        raise

    message.status = OutboundMessage.Status.SENT
    message.sent_at = timezone.now()
    message.last_error = ""
    message.body = ""
    message.save(
        update_fields=("status", "sent_at", "last_error", "body", "updated_at")
    )
    return message


def queued_message_ids(limit=100):
    stale_before = timezone.now() - timedelta(minutes=15)
    OutboundMessage.objects.filter(
        status=OutboundMessage.Status.PROCESSING, updated_at__lte=stale_before
    ).update(status=OutboundMessage.Status.QUEUED)
    return list(
        OutboundMessage.objects.filter(
            status__in=(
                OutboundMessage.Status.QUEUED,
                OutboundMessage.Status.FAILED,
            ),
            available_at__lte=timezone.now(),
            attempts__lt=MAX_DELIVERY_ATTEMPTS,
        )
        .order_by("available_at")
        .values_list("id", flat=True)[:limit]
    )
