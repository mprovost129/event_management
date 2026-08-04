from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from users.models import User


@pytest.mark.django_db
def test_platform_help_url_tracks_the_real_help_route_and_is_live(client):
    user = User.objects.create_user(
        email="member@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(user)

    response = client.get(reverse("sites:account_dashboard"))
    content = response.content.decode()

    help_path = reverse("core:help")
    assert f'href="http://localhost{help_path}"' in content
    assert client.get(help_path).status_code == 200


@pytest.mark.django_db
def test_signup_page_explains_trial_and_configured_pricing(client):
    response = client.get(reverse("users:signup"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "14 days free" in content
    assert "$20/month" in content
    assert "$220/year" in content
    assert "Create my account" in content


@pytest.mark.django_db
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
def test_password_change_uses_the_branded_templates_not_django_admin(client):
    user = User.objects.create_user(
        email="member@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(user)

    form_page = client.get(reverse("users:password_change"))
    assert form_page.status_code == 200
    used_templates = {
        template.name for template in form_page.templates if template.name
    }
    assert "registration/password_change_form.html" in used_templates
    assert not any(name.startswith("admin/") for name in used_templates)
    content = form_page.content.decode()
    assert "gh-auth-card" in content
    assert "admin/base_site.html" not in content

    response = client.post(
        reverse("users:password_change"),
        {
            "old_password": "Strong-Test-Pass-2026!",
            "new_password1": "Even-Stronger-Pass-2026!",
            "new_password2": "Even-Stronger-Pass-2026!",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("users:password_change_done")

    done_page = client.get(response.url)
    assert done_page.status_code == 200
    assert "gh-auth-card" in done_page.content.decode()

    user.refresh_from_db()
    assert user.check_password("Even-Stronger-Pass-2026!")
    # PasswordChangeView.form_valid() must rotate the session auth hash so the
    # user isn't logged out by their own password change.
    profile_page = client.get(reverse("users:profile"))
    assert profile_page.status_code == 200


@pytest.mark.django_db
def test_already_authenticated_user_visiting_login_is_redirected_to_dashboard(client):
    user = User.objects.create_user(
        email="member@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(user)

    response = client.get(reverse("users:login"))

    assert response.status_code == 302
    assert response.url == reverse("sites:account_dashboard")


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
@override_settings(RECAPTCHA_SITE_KEY="site", RECAPTCHA_SECRET_KEY="secret")
def test_signup_blocked_when_recaptcha_score_is_too_low(client):
    signup_payload = {
        "email": "leader@example.com",
        "first_name": "Dance",
        "last_name": "Leader",
        "password1": "Strong-Test-Pass-2026!",
        "password2": "Strong-Test-Pass-2026!",
        "recaptcha_token": "low-score-token",
    }
    with patch("core.recaptcha.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {
            "success": True,
            "action": "signup",
            "score": 0.1,
        }
        response = client.post(reverse("users:signup"), signup_payload)

    assert response.status_code == 200
    assert not User.objects.filter(email="leader@example.com").exists()
    assert "We could not verify this submission" in response.content.decode()


@pytest.mark.django_db
@override_settings(RECAPTCHA_SITE_KEY="site", RECAPTCHA_SECRET_KEY="secret")
def test_signup_succeeds_when_recaptcha_score_clears_the_threshold(client):
    signup_payload = {
        "email": "leader@example.com",
        "first_name": "Dance",
        "last_name": "Leader",
        "password1": "Strong-Test-Pass-2026!",
        "password2": "Strong-Test-Pass-2026!",
        "recaptcha_token": "good-token",
    }
    with patch("core.recaptcha.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        post.return_value.json.return_value = {
            "success": True,
            "action": "signup",
            "score": 0.9,
        }
        response = client.post(reverse("users:signup"), signup_payload)

    assert response.status_code == 302
    assert User.objects.filter(email="leader@example.com").exists()


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
