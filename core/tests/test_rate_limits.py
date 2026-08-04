from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import reverse

from core.rate_limits import client_address, public_write_rate_limit


@pytest.mark.django_db
@override_settings(
    PUBLIC_WRITE_RATE_LIMIT_MAX=2,
    PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS=90,
)
def test_public_signup_posts_are_limited_but_reads_remain_available(client):
    cache.clear()
    try:
        first = client.post(reverse("users:signup"), {})
        second = client.post(reverse("users:signup"), {})
        limited = client.post(reverse("users:signup"), {})
        read = client.get(reverse("users:signup"))

        assert first.status_code == 200
        assert second.status_code == 200
        assert limited.status_code == 429
        assert limited["Retry-After"] == "90"
        assert limited["Content-Security-Policy"].startswith("default-src 'self'")
        limited_content = limited.content.decode()
        assert "Too many attempts" in limited_content
        assert "ERROR 429" in limited_content
        assert read.status_code == 200
    finally:
        cache.clear()


def test_client_address_uses_only_the_configured_number_of_trusted_proxies():
    request = RequestFactory().post(
        "/",
        REMOTE_ADDR="10.0.0.2",
        HTTP_X_FORWARDED_FOR="198.51.100.8, 10.0.0.1",
    )

    with override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=0):
        assert client_address(request) == "10.0.0.2"
    with override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=1):
        assert client_address(request) == "198.51.100.8"
    with override_settings(RATE_LIMIT_TRUSTED_PROXY_COUNT=3):
        assert client_address(request) == "10.0.0.2"


def test_rate_limit_fails_open_when_cache_is_unavailable():
    request = RequestFactory().post("/", REMOTE_ADDR="198.51.100.8")
    view = public_write_rate_limit("test")(lambda request: HttpResponse("saved"))

    with patch("core.rate_limits.cache.add", side_effect=ConnectionError):
        response = view(request)

    assert response.status_code == 200
    assert response.content == b"saved"
