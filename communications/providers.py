import logging
import uuid
from dataclasses import dataclass

import resend
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


class DeliveryProviderError(Exception):
    pass


class ChannelNotConfigured(DeliveryProviderError):
    pass


@dataclass(frozen=True)
class DeliveryResult:
    provider: str
    message_id: str


class DjangoEmailProvider:
    name = "django"

    def send(self, message):
        headers = {}
        unsubscribe_url = getattr(message, "unsubscribe_url", "")
        if message.is_marketing and unsubscribe_url:
            headers = {
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        email = EmailMultiAlternatives(
            subject=message.subject,
            body=message.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[message.recipient_email],
            headers=headers,
        )
        if message.html_body:
            email.attach_alternative(message.html_body, "text/html")
        accepted = email.send(fail_silently=False)
        if accepted != 1:
            raise DeliveryProviderError("The email backend did not accept the message.")
        return DeliveryResult(provider=self.name, message_id=f"local-{message.id}")


class ResendEmailProvider:
    name = "resend"

    def send(self, message):
        if not settings.RESEND_API_KEY:
            raise ChannelNotConfigured("Resend email delivery requires RESEND_API_KEY.")
        headers = {"X-Gather-HQs-Message-ID": str(message.id)}
        if message.is_marketing and message.unsubscribe_url:
            headers.update(
                {
                    "List-Unsubscribe": f"<{message.unsubscribe_url}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                }
            )
        params = {
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [message.recipient_email],
            "subject": message.subject,
            "text": message.body,
            "headers": headers,
            "tags": [
                {"name": "site_id", "value": str(message.site_id)},
                {"name": "message_kind", "value": message.kind},
            ],
        }
        if message.html_body:
            params["html"] = message.html_body
        try:
            resend.api_key = settings.RESEND_API_KEY
            response = resend.Emails.send(
                params,
                {"idempotency_key": f"gather-hqs-message-{message.id}"},
            )
            provider_id = str(response["id"])
        except Exception as exc:
            raise DeliveryProviderError(
                "Resend did not accept the email message."
            ) from exc
        if not provider_id:
            raise DeliveryProviderError("Resend returned no email identifier.")
        return DeliveryResult(provider=self.name, message_id=provider_id)


class ConsoleSmsProvider:
    name = "console"

    def send(self, message):
        provider_id = f"console-{uuid.uuid4()}"
        logger.info(
            "Console SMS accepted message_id=%s site_id=%s",
            provider_id,
            message.site_id,
        )
        return DeliveryResult(provider=self.name, message_id=provider_id)


class DisabledSmsProvider:
    name = "disabled"

    def send(self, message):
        raise ChannelNotConfigured(
            "SMS sending is disabled until a delivery provider is configured."
        )


def provider_for(channel):
    if channel == "email":
        if settings.EMAIL_DELIVERY_BACKEND == "django":
            return DjangoEmailProvider()
        if settings.EMAIL_DELIVERY_BACKEND == "resend":
            return ResendEmailProvider()
        raise ChannelNotConfigured(
            f"Unknown email delivery backend: {settings.EMAIL_DELIVERY_BACKEND}."
        )
    if channel == "sms":
        if settings.SMS_DELIVERY_BACKEND == "console":
            return ConsoleSmsProvider()
        if settings.SMS_DELIVERY_BACKEND == "disabled":
            return DisabledSmsProvider()
        raise ChannelNotConfigured(
            f"Unknown SMS delivery backend: {settings.SMS_DELIVERY_BACKEND}."
        )
    raise ChannelNotConfigured(f"Unknown delivery channel: {channel}.")


def channel_is_configured(channel):
    if channel == "email":
        return settings.EMAIL_DELIVERY_BACKEND == "django" or (
            settings.EMAIL_DELIVERY_BACKEND == "resend"
            and bool(settings.RESEND_API_KEY)
        )
    if channel == "sms":
        return settings.SMS_DELIVERY_BACKEND != "disabled"
    return False
