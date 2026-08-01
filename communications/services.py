import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CampaignRecipient, OutboundMessage
from .providers import provider_for

logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 5
TERMINAL_MESSAGE_STATUSES = (
    OutboundMessage.Status.SENT,
    OutboundMessage.Status.DELIVERED,
    OutboundMessage.Status.BOUNCED,
    OutboundMessage.Status.OPENED,
    OutboundMessage.Status.CLICKED,
    OutboundMessage.Status.UNSUBSCRIBED,
    OutboundMessage.Status.SUPPRESSED,
)


def _validate_site_relationships(site, **relationships):
    for label, related in relationships.items():
        if related is not None and related.site_id != site.id:
            raise ValidationError(
                f"The outbound message {label} must belong to the same site."
            )


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
    recipient_email="",
    subject,
    body,
    html_body="",
    dedupe_key="",
    occurrence=None,
    registration=None,
    invitation=None,
    channel=OutboundMessage.Channel.EMAIL,
    recipient_phone="",
    contact=None,
    campaign=None,
    campaign_recipient=None,
    is_marketing=False,
    unsubscribe_url="",
    sms_segments=0,
    sms_allowance=None,
    dispatch=True,
):
    _validate_site_relationships(
        site,
        occurrence=occurrence,
        registration=registration,
        invitation=invitation,
        contact=contact,
        campaign=campaign,
        campaign_recipient=campaign_recipient,
        sms_allowance=sms_allowance,
    )
    values = {
        "kind": kind,
        "channel": channel,
        "recipient_email": recipient_email,
        "recipient_phone": recipient_phone,
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "occurrence": occurrence,
        "registration": registration,
        "invitation": invitation,
        "contact": contact,
        "campaign": campaign,
        "campaign_recipient": campaign_recipient,
        "is_marketing": is_marketing,
        "unsubscribe_url": unsubscribe_url,
        "sms_segments": sms_segments,
        "sms_allowance": sms_allowance,
    }
    if dedupe_key:
        message, created = OutboundMessage.objects.get_or_create(
            site=site, dedupe_key=dedupe_key, defaults=values
        )
    else:
        message = OutboundMessage.objects.create(site=site, **values)
        created = True
    if created and dispatch:
        transaction.on_commit(lambda: _dispatch_after_commit(message.id))
    return message


def _recipient_update(message, status, *, error=""):
    if not message.campaign_recipient_id:
        return
    values = {
        "status": status,
        "last_error": error[:1000],
        "updated_at": timezone.now(),
    }
    now = timezone.now()
    if status == CampaignRecipient.Status.SENT:
        values["sent_at"] = now
    elif status == CampaignRecipient.Status.DELIVERED:
        values["delivered_at"] = now
    elif status == CampaignRecipient.Status.OPENED:
        values["opened_at"] = now
    elif status == CampaignRecipient.Status.CLICKED:
        values["clicked_at"] = now
    elif status == CampaignRecipient.Status.UNSUBSCRIBED:
        values["unsubscribed_at"] = now
    CampaignRecipient.objects.filter(pk=message.campaign_recipient_id).update(**values)


def _recipient_is_still_reachable(message):
    if not message.contact_id:
        return True
    if message.is_marketing:
        from .campaigns import contact_eligibility

        allowed, _ = contact_eligibility(message.contact, message.channel)
        return allowed
    # Transactional mail (invitations, RSVP confirmations, reminders, review
    # requests) doesn't need marketing consent, but must not keep going to a
    # contact this platform already knows is archived or hard-suppressed
    # (bounced/complained) - checked here, at send time, so a contact who
    # became suppressed after the message was queued is still caught.
    from .campaigns import transactional_eligibility

    allowed, _ = transactional_eligibility(message.contact, message.channel)
    return allowed


def _finish_campaign(message):
    if message.campaign_id:
        from .campaigns import refresh_campaign_status

        refresh_campaign_status(message.campaign_id)


def _release_sms(message):
    if message.channel == OutboundMessage.Channel.SMS and message.sms_segments:
        from .campaigns import release_sms_for_message

        release_sms_for_message(message)


def _consume_sms(message):
    if message.channel == OutboundMessage.Channel.SMS and message.sms_segments:
        from .campaigns import consume_sms_for_message

        consume_sms_for_message(message)


def deliver_message(message_id):
    with transaction.atomic():
        message = (
            OutboundMessage.objects.select_for_update(of=("self",))
            .select_related(
                "contact", "campaign", "campaign_recipient", "sms_allowance"
            )
            .get(pk=message_id)
        )
        if message.status in TERMINAL_MESSAGE_STATUSES:
            return message
        if message.status == OutboundMessage.Status.PROCESSING:
            # A redelivered task (CELERY_TASK_ACKS_LATE, e.g. after a worker
            # is killed mid-send) can reach a message a prior, possibly still
            # in-flight attempt already claimed - the lock guarding that
            # write is released before the network call. Never send twice
            # from here; only the stale-PROCESSING reclaim in
            # queued_message_ids() may requeue a genuinely abandoned message.
            return message
        if message.attempts >= MAX_DELIVERY_ATTEMPTS:
            return message
        if message.available_at > timezone.now():
            return message
        if not _recipient_is_still_reachable(message):
            message.status = OutboundMessage.Status.SUPPRESSED
            message.body = ""
            message.html_body = ""
            message.unsubscribe_url = ""
            message.save(
                update_fields=(
                    "status",
                    "body",
                    "html_body",
                    "unsubscribe_url",
                    "updated_at",
                )
            )
            _recipient_update(message, CampaignRecipient.Status.SUPPRESSED)
            _release_sms(message)
            _finish_campaign(message)
            return message
        message.status = OutboundMessage.Status.PROCESSING
        message.attempts += 1
        message.save(update_fields=("status", "attempts", "updated_at"))

    try:
        result = provider_for(message.channel).send(message)
    except Exception as exc:
        message.status = OutboundMessage.Status.FAILED
        message.last_error = str(exc)[:1000]
        message.available_at = timezone.now() + timedelta(
            minutes=min(60, 2**message.attempts)
        )
        message.save(
            update_fields=("status", "last_error", "available_at", "updated_at")
        )
        if message.attempts >= MAX_DELIVERY_ATTEMPTS:
            _recipient_update(
                message, CampaignRecipient.Status.FAILED, error=message.last_error
            )
            _release_sms(message)
            message.body = ""
            message.html_body = ""
            message.unsubscribe_url = ""
            message.save(
                update_fields=(
                    "body",
                    "html_body",
                    "unsubscribe_url",
                    "updated_at",
                )
            )
            _finish_campaign(message)
        else:
            _recipient_update(
                message, CampaignRecipient.Status.QUEUED, error=message.last_error
            )
        raise

    message.status = OutboundMessage.Status.SENT
    message.sent_at = timezone.now()
    message.last_error = ""
    message.provider = result.provider
    message.provider_message_id = result.message_id
    message.body = ""
    message.html_body = ""
    message.unsubscribe_url = ""
    message.save(
        update_fields=(
            "status",
            "sent_at",
            "last_error",
            "provider",
            "provider_message_id",
            "body",
            "html_body",
            "unsubscribe_url",
            "updated_at",
        )
    )
    _recipient_update(message, CampaignRecipient.Status.SENT)
    _consume_sms(message)
    _finish_campaign(message)
    return message


def queued_message_ids(limit=None):
    limit = limit or settings.CAMPAIGN_DELIVERY_BATCH_SIZE
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
