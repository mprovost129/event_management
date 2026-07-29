from urllib.parse import urlsplit

import pytest
from django.core import mail
from django.urls import reverse

from users.models import User


def test_signup_page_explains_trial_and_configured_pricing(client):
    response = client.get(reverse("users:signup"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "14 days free" in content
    assert "$20/month" in content
    assert "$220/year" in content
    assert "Create my account" in content


def test_account_access_and_recovery_pages_share_clear_form_layout(client):
    for route in (
        "users:login",
        "users:password_reset",
        "users:resend_verification",
        "users:verification_sent",
    ):
        response = client.get(reverse(route))
        assert response.status_code == 200
        assert "gh-auth-card" in response.content.decode()


@pytest.mark.django_db
def test_password_reset_email_uses_public_gather_hqs_route(client):
    User.objects.create_user(
        email="leader@example.com", password="Strong-Test-Pass-2026!"
    )

    response = client.post(
        reverse("users:password_reset"), {"email": "leader@example.com"}
    )

    assert response.status_code == 302
    assert response.url == reverse("users:password_reset_done")
    assert len(mail.outbox) == 1
    reset_url = next(
        line for line in mail.outbox[0].body.splitlines() if line.startswith("http")
    )
    assert "/accounts/reset/" in reset_url
    reset_page = client.get(urlsplit(reset_url).path)
    assert reset_page.status_code == 302
    assert reset_page.url.endswith("/set-password/")
    form_page = client.get(reset_page.url)
    assert form_page.status_code == 200
    assert "gh-auth-card" in form_page.content.decode()


@pytest.mark.django_db
def test_signup_requires_email_verification_before_activation(client):
    response = client.post(
        reverse("users:signup"),
        {
            "email": "Leader@Example.com",
            "first_name": "Dance",
            "last_name": "Leader",
            "password1": "Strong-Test-Pass-2026!",
            "password2": "Strong-Test-Pass-2026!",
        },
    )

    assert response.status_code == 302
    user = User.objects.get(email="leader@example.com")
    assert not user.is_active
    assert not user.is_email_verified
    assert len(mail.outbox) == 1

    verification_url = next(
        line for line in mail.outbox[0].body.splitlines() if line.startswith("http")
    )
    verification_response = client.get(urlsplit(verification_url).path)

    user.refresh_from_db()
    assert verification_response.status_code == 302
    assert verification_response.url == reverse("sites:onboarding")
    assert user.is_active
    assert user.is_email_verified
    assert client.session.get("_auth_user_id") == str(user.pk)


@pytest.mark.django_db
def test_invalid_verification_link_does_not_activate_account(client):
    user = User.objects.create_user(
        email="inactive@example.com", password="Strong-Test-Pass-2026!", is_active=False
    )

    response = client.get(
        reverse(
            "users:verify_email",
            kwargs={"uidb64": str(user.pk), "token": "invalid-token"},
        )
    )

    user.refresh_from_db()
    assert response.status_code == 400
    assert not user.is_active
    assert not user.is_email_verified


@pytest.mark.django_db
def test_resend_verification_does_not_disclose_account_existence(client):
    response = client.post(
        reverse("users:resend_verification"), {"email": "missing@example.com"}
    )

    assert response.status_code == 302
    assert len(mail.outbox) == 0
