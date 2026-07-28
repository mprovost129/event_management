import pytest
from django.urls import reverse

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
