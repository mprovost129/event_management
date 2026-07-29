import resend
from django.conf import settings

from .callbacks import process_provider_callback

EVENT_TYPES = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.failed": "failed",
    "email.opened": "opened",
    "email.clicked": "clicked",
    "email.suppressed": "suppressed",
}


def process_resend_webhook(*, body, webhook_id, timestamp, signature):
    payload = resend.Webhooks.verify(
        {
            "payload": body.decode("utf-8"),
            "headers": {
                "id": webhook_id,
                "timestamp": timestamp,
                "signature": signature,
            },
            "webhook_secret": settings.RESEND_WEBHOOK_SECRET,
        }
    )
    event_type = EVENT_TYPES.get(str(payload.get("type", "")))
    data = payload.get("data") or {}
    provider_message_id = str(data.get("email_id", ""))
    if not event_type or not provider_message_id:
        return None
    return process_provider_callback(
        provider="resend",
        provider_event_id=webhook_id[:255],
        provider_message_id=provider_message_id[:255],
        event_type=event_type,
        occurred_at=payload.get("created_at"),
    )
