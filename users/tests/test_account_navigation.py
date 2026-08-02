import pytest
from django.test import RequestFactory

from sites.services import create_subscriber_site
from users.context_processors import account_navigation
from users.models import User


@pytest.mark.django_db
def test_nav_primary_site_url_preserves_localhost_dev_port():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Marketing",
        slug="marketing",
        timezone_name="America/New_York",
    )
    site.is_published = True
    site.save(update_fields=["is_published"])

    request = RequestFactory().get("/dashboard/", HTTP_HOST="localhost:8000")
    request.user = owner

    context = account_navigation(request)

    assert context["nav_primary_site_url"] == "http://marketing.localhost:8000"


@pytest.mark.django_db
def test_nav_primary_site_url_does_not_append_port_for_non_local_domains():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Marketing",
        slug="marketing",
        timezone_name="America/New_York",
    )
    domain = site.domains.get(is_canonical=True)
    domain.hostname = "marketing.example.com"
    domain.save(update_fields=["hostname"])
    site.is_published = True
    site.save(update_fields=["is_published"])

    request = RequestFactory().get("/dashboard/", HTTP_HOST="localhost:8000")
    request.user = owner

    context = account_navigation(request)

    assert context["nav_primary_site_url"] == "http://marketing.example.com"
