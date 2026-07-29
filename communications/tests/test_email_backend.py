from unittest.mock import patch

import pytest
from django.core.mail import EmailMultiAlternatives
from django.test import override_settings

from communications.email_backend import (
    ResendEmailBackend,
    ResendEmailBackendError,
)


@override_settings(
    RESEND_API_KEY="re_test_account_email",
    DEFAULT_FROM_EMAIL="Gather HQs <events@gatherhqs.com>",
)
@patch("communications.email_backend.resend.Emails.send")
def test_resend_backend_delivers_django_account_email(send):
    send.return_value = {"id": "email_account_123"}
    message = EmailMultiAlternatives(
        subject="Verify your Gather HQs account",
        body="Use the verification link.",
        from_email=None,
        to=["leader@example.com"],
        reply_to=["support@gatherhqs.com"],
        headers={"X-Account-Email": "verification"},
    )
    message.attach_alternative("<p>Use the verification link.</p>", "text/html")

    accepted = ResendEmailBackend().send_messages([message])

    assert accepted == 1
    params = send.call_args.args[0]
    assert params == {
        "from": "Gather HQs <events@gatherhqs.com>",
        "to": ["leader@example.com"],
        "subject": "Verify your Gather HQs account",
        "text": "Use the verification link.",
        "reply_to": ["support@gatherhqs.com"],
        "headers": {"X-Account-Email": "verification"},
        "html": "<p>Use the verification link.</p>",
    }


@override_settings(RESEND_API_KEY="")
def test_resend_backend_requires_api_key():
    message = EmailMultiAlternatives(
        subject="Verify",
        body="Verify your account.",
        to=["leader@example.com"],
    )

    with pytest.raises(ResendEmailBackendError):
        ResendEmailBackend().send_messages([message])


@override_settings(RESEND_API_KEY="")
def test_resend_backend_honors_fail_silently():
    message = EmailMultiAlternatives(
        subject="Verify",
        body="Verify your account.",
        to=["leader@example.com"],
    )

    assert ResendEmailBackend(fail_silently=True).send_messages([message]) == 0
