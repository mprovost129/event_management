import resend
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackendError(Exception):
    pass


class ResendEmailBackend(BaseEmailBackend):
    """Deliver Django account emails through the Resend HTTPS API."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not settings.RESEND_API_KEY:
            return self._fail("Resend email delivery requires RESEND_API_KEY.")

        resend.api_key = settings.RESEND_API_KEY
        sent = 0
        for message in email_messages:
            if message.attachments:
                if self.fail_silently:
                    continue
                raise ResendEmailBackendError(
                    "The Gather HQs Resend backend does not support attachments."
                )
            params = {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(message.to),
                "subject": message.subject,
                "text": message.body,
            }
            if message.cc:
                params["cc"] = list(message.cc)
            if message.bcc:
                params["bcc"] = list(message.bcc)
            if message.reply_to:
                params["reply_to"] = list(message.reply_to)
            if message.extra_headers:
                params["headers"] = dict(message.extra_headers)
            for alternative in getattr(message, "alternatives", ()):
                if alternative.mimetype == "text/html":
                    params["html"] = alternative.content
                    break
            try:
                response = resend.Emails.send(params)
                if not response.get("id"):
                    raise ResendEmailBackendError(
                        "Resend returned no email identifier."
                    )
            except Exception as exc:
                if self.fail_silently:
                    continue
                if isinstance(exc, ResendEmailBackendError):
                    raise
                raise ResendEmailBackendError(
                    "Resend did not accept the Django email message."
                ) from exc
            sent += 1
        return sent

    def _fail(self, message):
        if self.fail_silently:
            return 0
        raise ResendEmailBackendError(message)
