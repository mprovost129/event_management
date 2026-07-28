import logging
import uuid
from dataclasses import dataclass

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
        accepted = email.send(fail_silently=False)
        if accepted != 1:
            raise DeliveryProviderError("The email backend did not accept the message.")
        return DeliveryResult(provider=self.name, message_id=f"local-{message.id}")


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
        if settings.EMAIL_DELIVERY_BACKEND != "django":
            raise ChannelNotConfigured(
                f"Unknown email delivery backend: {settings.EMAIL_DELIVERY_BACKEND}."
            )
        return DjangoEmailProvider()
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
        return settings.EMAIL_DELIVERY_BACKEND == "django"
    if channel == "sms":
        return settings.SMS_DELIVERY_BACKEND != "disabled"
    return False
