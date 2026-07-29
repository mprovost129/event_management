import pytest
from django.test import override_settings
from django.urls import reverse

from core.checks import deployment_product_check
from ops.models import SystemHeartbeat
from ops.tasks import record_background_heartbeat


@pytest.mark.django_db
def test_health_endpoints_distinguish_liveness_and_dependency_readiness(client):
    live = client.get(reverse("core:health_live"))
    ready = client.get(reverse("core:health_ready"))

    assert live.status_code == 200
    assert live.json() == {"ok": True, "service": "web"}
    assert ready.status_code == 200
    assert ready.json()["checks"] == {
        "database": True,
        "redis": True,
        "worker": True,
        "scheduler": True,
    }


@pytest.mark.django_db
def test_readiness_requires_recent_worker_and_scheduler_heartbeat(client, settings):
    settings.HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS = True

    stale = client.get(reverse("core:health_ready"))
    assert stale.status_code == 503
    assert stale.json()["checks"]["worker"] is False
    assert stale.json()["checks"]["scheduler"] is False

    record_background_heartbeat()

    healthy = client.get(reverse("core:health_ready"))
    assert healthy.status_code == 200
    assert healthy.json()["ok"] is True
    assert set(SystemHeartbeat.objects.values_list("key", flat=True)) == {
        "scheduler_dispatch_observed",
        "worker_execution",
    }


@pytest.mark.django_db
def test_global_security_headers_skip_link_and_legal_drafts_are_exposed(client):
    response = client.get(reverse("core:home"))

    assert response.status_code == 200
    assert response["Content-Security-Policy"].startswith("default-src 'self'")
    assert response["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    assert b'href="#main-content"' in response.content

    for route in (
        "core:privacy",
        "core:terms",
        "core:acceptable_use",
        "core:review_guidelines",
    ):
        legal = client.get(reverse(route))
        assert legal.status_code == 200
        assert b"Pre-launch policy draft" in legal.content


def test_platform_home_explains_trial_pricing_and_social_preview(client):
    response = client.get(reverse("core:home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Your group has plans" in content
    assert "Start your 14-day free trial" in content
    assert ">20<" in content
    assert ">220<" in content
    assert "No Gather HQs fee on tickets or member dues" in content
    assert 'property="og:image"' in content
    assert "/static/img/gather-hqs-social.png" in content


@pytest.mark.django_db
def test_production_error_pages_are_safe_branded_and_traceable(client):
    missing = client.get(
        "/definitely-not-a-real-page/",
        headers={"X-Request-ID": "launch-error-request-123"},
    )

    assert missing.status_code == 404
    assert b"Page not found" in missing.content
    assert b"launch-error-request-123" in missing.content
    assert missing["X-Request-ID"] == "launch-error-request-123"
    assert missing["Content-Security-Policy"].startswith("default-src 'self'")


@pytest.mark.django_db
@override_settings(SUPPORT_EMAIL="support@gatherhqs.com")
def test_support_contact_is_published_in_policy_and_error_pages(client):
    privacy = client.get(reverse("core:privacy"))
    missing = client.get("/missing-support-test/")

    assert b"mailto:support@gatherhqs.com" in privacy.content
    assert b"mailto:support@gatherhqs.com" in missing.content


@override_settings(
    DEBUG=False,
    EMAIL_DELIVERY_BACKEND="resend",
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    RESEND_API_KEY="",
    RESEND_WEBHOOK_SECRET="",
)
def test_resend_deployment_requires_api_and_webhook_secrets():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E026" in issue_ids
    assert "platform.E027" in issue_ids
    assert "platform.E014" not in issue_ids


@override_settings(
    DEBUG=False,
    EMAIL_DELIVERY_BACKEND="resend",
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    RESEND_API_KEY="re_configured",
    RESEND_WEBHOOK_SECRET="whsec_configured",
)
def test_resend_deployment_accepts_complete_provider_configuration():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E026" not in issue_ids
    assert "platform.E027" not in issue_ids
    assert "platform.E014" not in issue_ids
    assert "platform.W003" not in issue_ids
