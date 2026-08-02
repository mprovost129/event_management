import pytest
from django.test import RequestFactory, override_settings
from django.urls import reverse

from core.context_processors import platform
from sites.services import create_subscriber_site
from users.models import User


@pytest.mark.django_db
def test_standard_admin_path_redirects_to_the_canonical_platform_admin(client):
    response = client.get("/admin/")

    assert response.status_code == 302
    assert response.url == reverse("admin:index")
    assert response.url == "/platform-admin/"


@pytest.mark.django_db
def test_superuser_can_open_admin_and_sees_navigation_link(client):
    admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(admin)

    admin_response = client.get(reverse("admin:index"))
    dashboard_response = client.get(reverse("sites:account_dashboard"))

    assert admin_response.status_code == 200
    assert "Site administration" in admin_response.content.decode()
    assert "http://localhost/admin/" in dashboard_response.content.decode()
    assert "http://localhost/platform-ops/" in dashboard_response.content.decode()
    assert ">Admin</a>" in dashboard_response.content.decode()
    assert ">Platform operations</a>" in dashboard_response.content.decode()


@pytest.mark.django_db
def test_non_superuser_does_not_see_platform_admin_or_ops_links(client):
    user = User.objects.create_user(
        email="member@example.com",
        password="Strong-Test-Pass-2026!",
    )
    client.force_login(user)

    response = client.get(reverse("sites:account_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Platform operations" not in content
    assert ">Admin</a>" not in content


@pytest.mark.django_db
def test_platform_admin_routes_are_not_exposed_on_tenant_subdomains(client):
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
    )
    create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )

    for path in ("/admin/", "/platform-admin/", "/platform-ops/"):
        response = client.get(path, headers={"host": "boot-scooters.localhost"})
        assert response.status_code == 404, path


@pytest.mark.django_db
@override_settings(
    DEBUG=False,
    PLATFORM_DOMAIN="gatherhqs.com",
    PLATFORM_CONTROL_HOSTS=("gatherhqs.com", "www.gatherhqs.com"),
    ALLOWED_HOSTS=("gatherhqs.com", "www.gatherhqs.com"),
)
def test_control_links_preserve_current_control_host_and_dev_port(client):
    admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(admin)

    redirected = client.get(
        reverse("sites:account_dashboard"),
        headers={"host": "www.gatherhqs.com:8000"},
    )
    response = client.get(
        reverse("sites:account_dashboard"),
        headers={"host": "gatherhqs.com:8000"},
    )
    content = response.content.decode()

    assert redirected.status_code == 302
    assert redirected.url == "http://gatherhqs.com:8000/dashboard/"
    assert response.status_code == 200
    assert "http://gatherhqs.com:8000/admin/" in content
    assert "http://gatherhqs.com:8000/platform-ops/" in content


@pytest.mark.django_db
@override_settings(
    DEBUG=True,
    PLATFORM_DOMAIN="localhost",
    PLATFORM_CONTROL_HOSTS=("localhost", "www.localhost"),
    ALLOWED_HOSTS=("localhost", "www.localhost"),
)
def test_debug_mode_prefers_local_loopback_control_links(client):
    admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    request = RequestFactory().get("/dashboard/", HTTP_HOST="localhost:8000")
    request.user = admin

    context = platform(request)

    assert context["platform_admin_url"] == "http://127.0.0.1:8000/admin/"
    assert context["platform_ops_url"] == "http://127.0.0.1:8000/platform-ops/"
