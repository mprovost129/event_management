import json
import logging
import re

import pytest
from django.conf import settings
from django.test import RequestFactory, override_settings
from django.urls import reverse

from config.storage import normalize_s3_endpoint
from core.checks import deployment_product_check, product_configuration_check
from core.logging import JsonFormatter, RequestContextFilter
from ops.models import SystemHeartbeat
from ops.tasks import record_background_heartbeat
from users.models import User


def test_data_tables_and_images_keep_baseline_accessibility_markup():
    failures = []
    for template in (settings.BASE_DIR / "templates").rglob("*.html"):
        source = template.read_text(encoding="utf-8")
        failures.extend(
            f"{template.relative_to(settings.BASE_DIR)}: {header}"
            for header in re.findall(r"<th\b[^>]*>", source, flags=re.IGNORECASE)
            if not re.search(r"\bscope=[\"'](?:col|row)[\"']", header)
        )
        failures.extend(
            f"{template.relative_to(settings.BASE_DIR)}: {image}"
            for image in re.findall(r"<img\b[^>]*>", source, flags=re.IGNORECASE)
            if not re.search(r"\balt=[\"']", image)
        )
        responsive_regions = re.findall(
            r'<div\b[^>]*class="[^"]*\btable-responsive\b[^"]*"[^>]*>', source
        )
        failures.extend(
            f"{template.relative_to(settings.BASE_DIR)}: {region}"
            for region in responsive_regions
            if (
                'role="region"' not in region
                or 'tabindex="0"' not in region
                or not re.search(r'\baria-label(?:ledby)?="', region)
            )
        )

    assert not failures


def test_no_template_relies_on_an_inline_event_handler_the_csp_blocks():
    # SecurityHeadersMiddleware sends script-src 'self' with no 'unsafe-inline',
    # so a browser silently drops onclick=/onsubmit=/etc. attributes rather than
    # running them - the form still submits, just with no confirmation.
    # Destructive actions must use the data-confirm attribute main.js listens for.
    failures = []
    for template in (settings.BASE_DIR / "templates").rglob("*.html"):
        source = template.read_text(encoding="utf-8")
        failures.extend(
            f"{template.relative_to(settings.BASE_DIR)}: {match}"
            for match in re.findall(
                r'\bon[a-z]+\s*=\s*"[^"]*"', source, flags=re.IGNORECASE
            )
        )

    assert not failures


@override_settings(RELEASE_VERSION="release-abc123")
def test_structured_logs_include_the_release_identifier():
    record = logging.LogRecord(
        name="release-test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Release logging works",
        args=(),
        exc_info=None,
    )
    RequestContextFilter().filter(record)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["release"] == "release-abc123"


def test_structured_logs_include_request_diagnostics_for_404_records():
    request = RequestFactory().get(
        "/platform-ops/",
        HTTP_HOST="tenant.localhost",
        REMOTE_ADDR="10.20.30.40",
        HTTP_X_FORWARDED_FOR="198.51.100.20",
    )
    record = logging.LogRecord(
        name="django.request",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Not Found: /platform-ops/",
        args=(),
        exc_info=None,
    )
    record.request = request
    record.status_code = 404
    RequestContextFilter().filter(record)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["status_code"] == 404
    assert payload["request_host"] == "tenant.localhost"
    assert payload["request_path"] == "/platform-ops/"
    assert payload["request_method"] == "GET"
    assert payload["request_scheme"] == "http"
    assert payload["request_route"] == "-"
    assert payload["actor_user_id"] is None
    assert payload["actor_is_superuser"] is None
    assert payload["client_ip"] == "10.20.30.40"
    assert payload["forwarded_for"] == "198.51.100.20"
    assert payload["platform_route_on_non_control_host"] is True


@override_settings(PLATFORM_CONTROL_HOSTS=("control.gatherhqs.com",))
def test_structured_logs_mark_platform_route_as_control_host_when_expected():
    request = RequestFactory().get(
        "/platform-ops/",
        HTTP_HOST="control.gatherhqs.com",
    )
    record = logging.LogRecord(
        name="django.request",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Not Found: /platform-ops/",
        args=(),
        exc_info=None,
    )
    record.request = request
    record.status_code = 404
    RequestContextFilter().filter(record)

    payload = json.loads(JsonFormatter().format(record))

    assert payload["platform_route_on_non_control_host"] is False


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
    assert "3% Gather HQs fee on paid tickets; no fee on member dues" in content
    assert "deducted from your group's proceeds" in content
    assert 'property="og:image"' in content
    assert "/static/img/gather-hqs-social.png" in content


@pytest.mark.django_db
def test_already_authenticated_user_visiting_platform_home_is_sent_to_dashboard(
    client,
):
    user = User.objects.create_user(
        email="member@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(user)

    response = client.get(reverse("core:home"))

    assert response.status_code == 302
    assert response.url == reverse("sites:account_dashboard")


def test_help_center_page_is_available_with_feature_guidance(client):
    response = client.get(reverse("core:help"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "How to use Gather HQs" in content
    assert "Notifications and communications" in content
    assert "Support and operations" in content


@override_settings(
    DOCUMENT_UPLOAD_MAX_BYTES=0,
    DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS=("pdf", "../exe"),
)
def test_document_upload_configuration_rejects_unsafe_limits_and_extensions():
    issue_ids = {issue.id for issue in product_configuration_check(None)}

    assert "platform.E029" in issue_ids
    assert "platform.E030" in issue_ids


@override_settings(
    DOCUMENT_UPLOAD_SCAN_BACKEND="unsupported",
    CLAMAV_PORT=0,
    CLAMAV_TIMEOUT_SECONDS=0,
)
def test_document_scanner_configuration_rejects_invalid_values():
    issue_ids = {issue.id for issue in product_configuration_check(None)}

    assert "platform.E031" in issue_ids
    assert "platform.E032" in issue_ids


@override_settings(
    DOCUMENT_UPLOAD_SCAN_BACKEND="cloudmersive",
    CLOUDMERSIVE_API_URL="http://api.cloudmersive.com/virus/scan/file/advanced",
    CLOUDMERSIVE_TIMEOUT_SECONDS=0,
)
def test_cloudmersive_scanner_configuration_requires_https_and_positive_timeout():
    issue_ids = {issue.id for issue in product_configuration_check(None)}

    assert "platform.E036" in issue_ids
    assert "platform.E037" in issue_ids


@override_settings(DEBUG=False, DOCUMENT_UPLOAD_SCAN_BACKEND="disabled")
def test_production_deployment_requires_document_malware_scanning():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E033" in issue_ids


@override_settings(
    DEBUG=False,
    MEDIA_STORAGE_BACKEND="s3",
    AWS_S3_ENDPOINT_URL=(
        "https://example-bucket.s3.us-east-1.amazonaws.com/media/example-bucket"
    ),
)
def test_production_deployment_warns_when_aws_object_url_is_used_as_endpoint():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.W005" in issue_ids


@override_settings(
    DEBUG=False,
    MEDIA_STORAGE_BACKEND="s3",
    AWS_S3_SIGNATURE_VERSION="s3",
)
def test_production_deployment_requires_s3_signature_version_4():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E039" in issue_ids


def test_aws_endpoint_normalization_preserves_legacy_object_prefix():
    endpoint_url, location = normalize_s3_endpoint(
        "https://example-bucket.s3.us-east-1.amazonaws.com/media/example-bucket",
    )

    assert endpoint_url is None
    assert location == "media/example-bucket"


def test_non_aws_s3_compatible_endpoint_is_preserved():
    endpoint_url, location = normalize_s3_endpoint(
        "https://objects.example.com",
        "media",
    )

    assert endpoint_url == "https://objects.example.com"
    assert location == "media"


@override_settings(
    DEBUG=False,
    DOCUMENT_UPLOAD_SCAN_BACKEND="cloudmersive",
    CLOUDMERSIVE_API_KEY="",
)
def test_production_cloudmersive_scanning_requires_api_key():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E038" in issue_ids


@override_settings(
    DEBUG=False,
    PLATFORM_DOMAIN="gatherhqs.com",
    SESSION_COOKIE_DOMAIN=".gatherhqs.com",
    CSRF_COOKIE_DOMAIN=".gatherhqs.com",
)
def test_production_deployment_rejects_cross_subdomain_auth_cookies():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E034" in issue_ids
    assert "platform.E035" in issue_ids


@override_settings(
    DEBUG=False,
    PLATFORM_DOMAIN="gatherhqs.com",
    SESSION_COOKIE_DOMAIN=None,
    CSRF_COOKIE_DOMAIN=None,
)
def test_production_deployment_accepts_host_only_auth_cookies():
    issue_ids = {issue.id for issue in deployment_product_check(None)}

    assert "platform.E034" not in issue_ids
    assert "platform.E035" not in issue_ids


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
def test_unrecognized_tenant_subdomain_404_still_gets_clickjacking_protection(client):
    response = client.get("/", headers={"host": "totally-unknown-tenant.localhost"})

    assert response.status_code == 404
    assert response["X-Frame-Options"] == "DENY"
    assert response["Content-Security-Policy"].startswith("default-src 'self'")


@pytest.mark.django_db
def test_marketing_navbar_variant_falls_back_to_the_authenticated_navbar_when_logged_in():
    from django.template.loader import render_to_string

    request = RequestFactory().get("/")
    request.user = User.objects.create_user(
        email="member@example.com", password="Strong-Test-Pass-2026!"
    )

    html = render_to_string(
        "partials/navbar.html", {"navbar_variant": "marketing"}, request=request
    )

    assert "Start free" not in html
    assert "gh-navbar-actions" not in html
    assert reverse("sites:account_dashboard") in html


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
