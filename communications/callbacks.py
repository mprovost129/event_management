from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from contacts.models import ConsentStatus
from contacts.services import set_consent_status

from .models import CampaignRecipient, OutboundMessage, ProviderCallbackEvent

EVENT_STATUS = {
    "sent": OutboundMessage.Status.SENT,
    "delivered": OutboundMessage.Status.DELIVERED,
    "bounced": OutboundMessage.Status.BOUNCED,
    "complained": OutboundMessage.Status.BOUNCED,
    "failed": OutboundMessage.Status.FAILED,
    "opened": OutboundMessage.Status.OPENED,
    "clicked": OutboundMessage.Status.CLICKED,
    "unsubscribed": OutboundMessage.Status.UNSUBSCRIBED,
    "suppressed": OutboundMessage.Status.SUPPRESSED,
}
RECIPIENT_STATUS = {
    "sent": CampaignRecipient.Status.SENT,
    "delivered": CampaignRecipient.Status.DELIVERED,
    "bounced": CampaignRecipient.Status.BOUNCED,
    "complained": CampaignRecipient.Status.BOUNCED,
    "failed": CampaignRecipient.Status.FAILED,
    "opened": CampaignRecipient.Status.OPENED,
    "clicked": CampaignRecipient.Status.CLICKED,
    "unsubscribed": CampaignRecipient.Status.UNSUBSCRIBED,
    "suppressed": CampaignRecipient.Status.SUPPRESSED,
}
ENGAGEMENT_RANK = {
    OutboundMessage.Status.SENT: 1,
    OutboundMessage.Status.DELIVERED: 2,
    OutboundMessage.Status.OPENED: 3,
    OutboundMessage.Status.CLICKED: 4,
    OutboundMessage.Status.FAILED: 90,
    OutboundMessage.Status.BOUNCED: 100,
    OutboundMessage.Status.SUPPRESSED: 105,
    OutboundMessage.Status.UNSUBSCRIBED: 110,
}


def _event_time(value):
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is not None:
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed)
            return parsed
    return datetime.fromtimestamp(float(value), tz=timezone.get_current_timezone())


def process_provider_callback(
    *, provider, provider_event_id, provider_message_id, event_type, occurred_at=None
):
    callback, created = ProviderCallbackEvent.objects.get_or_create(
        provider=provider,
        provider_event_id=provider_event_id,
        defaults={
            "provider_message_id": provider_message_id,
            "event_type": event_type,
        },
    )
    if not created and callback.status in (
        ProviderCallbackEvent.Status.PROCESSED,
        ProviderCallbackEvent.Status.IGNORED,
    ):
        return callback
    try:
        with transaction.atomic():
            callback = ProviderCallbackEvent.objects.select_for_update().get(
                pk=callback.pk
            )
            message = (
                OutboundMessage.objects.select_for_update()
                .select_related("contact", "campaign_recipient")
                .filter(provider=provider, provider_message_id=provider_message_id)
                .first()
            )
            mapped = EVENT_STATUS.get(event_type)
            if message is None or mapped is None:
                callback.status = ProviderCallbackEvent.Status.IGNORED
                callback.processed_at = timezone.now()
                callback.save(update_fields=("status", "processed_at"))
                return callback
            event_time = _event_time(occurred_at)
            current_rank = ENGAGEMENT_RANK.get(message.status, 0)
            mapped_rank = ENGAGEMENT_RANK.get(mapped, 0)
            status_advanced = mapped_rank >= current_rank
            if status_advanced:
                message.status = mapped
            message_updates = ["status", "updated_at"]
            if event_type == "failed":
                # A provider's final failure callback must not be picked up as a
                # local transient delivery failure and sent a second time.
                message.attempts = max(message.attempts, 5)
                message_updates.append("attempts")
            timestamp_field = {
                "sent": "sent_at",
                "delivered": "delivered_at",
                "opened": "opened_at",
                "clicked": "clicked_at",
                "unsubscribed": "unsubscribed_at",
            }.get(event_type)
            if timestamp_field and getattr(message, timestamp_field) is None:
                setattr(message, timestamp_field, event_time)
                message_updates.append(timestamp_field)
            message.save(update_fields=message_updates)

            if message.campaign_recipient_id:
                recipient = CampaignRecipient.objects.select_for_update().get(
                    pk=message.campaign_recipient_id
                )
                if status_advanced:
                    recipient.status = RECIPIENT_STATUS[event_type]
                recipient_updates = ["status", "updated_at"]
                if (
                    recipient.last_event_at is None
                    or event_time > recipient.last_event_at
                ):
                    recipient.last_event_at = event_time
                    recipient_updates.append("last_event_at")
                if timestamp_field and getattr(recipient, timestamp_field) is None:
                    setattr(recipient, timestamp_field, event_time)
                    recipient_updates.append(timestamp_field)
                recipient.save(update_fields=recipient_updates)

            if message.contact_id and event_type in (
                "bounced",
                "complained",
                "suppressed",
                "unsubscribed",
            ):
                status = (
                    ConsentStatus.WITHDRAWN
                    if event_type == "unsubscribed"
                    else ConsentStatus.SUPPRESSED
                )
                set_consent_status(
                    contact=message.contact,
                    channel=message.channel,
                    status=status,
                    source=f"{provider}_{event_type}",
                )
            callback.status = ProviderCallbackEvent.Status.PROCESSED
            callback.error = ""
            callback.processed_at = timezone.now()
            callback.save(update_fields=("status", "error", "processed_at"))
    except Exception as exc:
        ProviderCallbackEvent.objects.filter(pk=callback.pk).update(
            status=ProviderCallbackEvent.Status.FAILED,
            error=str(exc)[:2000],
        )
        raise
    return callback
