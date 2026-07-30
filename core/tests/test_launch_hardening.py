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
def test_global_security_headers_skip_link_and_legal_center_are_exposed(client):
    response = client.get(reverse("core:home"))

    assert response.status_code == 200
    assert response["Content-Security-Policy"].startswith("default-src 'self'")
    assert response["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    assert b'href="#main-content"' in response.content

    for route in (
        "core:legal",
        "core:privacy",
        "core:terms",
        "core:cookies",
        "core:refunds",
        "core:acceptable_use",
        "core:retention",
        "core:security",
        "core:review_guidelines",
    ):
        legal = client.get(reverse(route))
        assert legal.status_code == 200
        assert b"Pre-launch policy draft" in legal.content
        assert b'name="robots" content="noindex,nofollow"' in legal.content
        assert b'rel="canonical"' in legal.content


@override_settings(LEGAL_DRAFT=False)
def test_approved_legal_pages_are_indexable(client):
    terms = client.get(reverse("core:terms"))

    assert terms.status_code == 200
    assert b'name="robots" content="noindex,nofollow"' not in terms.content


def test_legal_pages_cover_product_specific_roles_and_flows(client):
    terms = client.get(reverse("core:terms")).content.decode()
    privacy = client.get(reverse("core:privacy")).content.decode()
    refunds = client.get(reverse("core:refunds")).content.decode()
    retention = client.get(reverse("core:retention")).content.decode()

    assert "technology provider—not the organizer" in terms
    assert "14-day no-card trial" in terms
    assert "connected Stripe account" in terms
    assert "Subscriber-controlled information" in privacy
    assert "children under 13" in privacy
    assert "Platform subscriptions" in refunds
    assert "Event tickets and membership dues" in refunds
    assert "90 days" in retention


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
    LEGAL_DRAFT=True,
    LEGAL_POSTAL_ADDRESS="",
)
def test_deployment_blocks_unapproved_or_unidentified_legal_policies():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E029" in issue_ids
    assert "platform.E030" in issue_ids


@override_settings(
    DEBUG=False,
    LEGAL_DRAFT=False,
    LEGAL_POSTAL_ADDRESS="PO Box 123, Swansea, MA 02777",
)
def test_deployment_accepts_reviewed_legal_configuration():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E029" not in issue_ids
    assert "platform.E030" not in issue_ids


@override_settings(
    DEBUG=False,
    EMAIL_DELIVERY_BACKEND="resend",
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    RESEND_API_KEY="",
    RESEND_WEBHOOK_SECRET="",
)
def test_resend_deployment_requires_api_and_webhook_secrets():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E028" in issue_ids
    assert "platform.E026" in issue_ids
    assert "platform.E027" in issue_ids
    assert "platform.E014" not in issue_ids


@override_settings(
    DEBUG=False,
    EMAIL_DELIVERY_BACKEND="resend",
    EMAIL_BACKEND="communications.email_backend.ResendEmailBackend",
    RESEND_API_KEY="re_configured",
    RESEND_WEBHOOK_SECRET="whsec_configured",
)
def test_resend_deployment_accepts_complete_provider_configuration():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E028" not in issue_ids
    assert "platform.E026" not in issue_ids
    assert "platform.E027" not in issue_ids
    assert "platform.E014" not in issue_ids
    assert "platform.W003" not in issue_ids
