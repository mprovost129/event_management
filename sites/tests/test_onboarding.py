from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from ops.models import AuditEvent
from sites.models import Site, SiteDomain, SiteRole, SiteTheme
from sites.services import create_subscriber_site
from subscriptions.models import PlatformSubscription
from users.models import User


def verified_user(email):
    return User.objects.create_user(
        email=email,
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )


@pytest.mark.django_db
def test_onboarding_creates_isolated_site_trial_and_owner_role(client, settings):
    owner = verified_user("owner@example.com")
    client.force_login(owner)

    response = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Boot Scooters",
            "slug": "boot-scooters",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )

    site = Site.objects.get(slug="boot-scooters")
    subscription = site.platform_subscription
    assert response.status_code == 302
    assert response.url == reverse("sites:dashboard", kwargs={"site_id": site.id})
    assert site.status == Site.Status.TRIALING
    assert SiteDomain.objects.get(site=site).hostname == "boot-scooters.localhost"
    assert SiteTheme.objects.filter(site=site).exists()
    assert SiteRole.objects.get(site=site, user=owner).role == (
        SiteRole.Role.SUBSCRIBER_ADMIN
    )
    assert subscription.status == PlatformSubscription.Status.TRIALING
    assert subscription.trial_ends_at == pytest.approx(
        subscription.trial_started_at
        + timedelta(days=settings.SUBSCRIPTION_TRIAL_DAYS),
        abs=timedelta(seconds=1),
    )
    assert AuditEvent.objects.filter(action="site.created", site_id=site.id).exists()


@pytest.mark.django_db
def test_reserved_site_slug_is_rejected(client):
    owner = verified_user("owner@example.com")
    client.force_login(owner)

    response = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Admin Group",
            "slug": "admin",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )

    assert response.status_code == 200
    assert "reserved" in response.content.decode().lower()
    assert not Site.objects.exists()


@pytest.mark.django_db
def test_site_dashboard_is_denied_across_tenants(client):
    owner = verified_user("owner@example.com")
    outsider = verified_user("outsider@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    client.force_login(outsider)

    response = client.get(reverse("sites:dashboard", kwargs={"site_id": site.id}))

    assert response.status_code == 403


@pytest.mark.django_db
def test_subscriber_admin_can_add_manager_but_manager_cannot_add_managers(client):
    owner = verified_user("owner@example.com")
    manager = verified_user("manager@example.com")
    another = verified_user("another@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    client.force_login(owner)

    add_response = client.post(
        reverse("sites:add_manager", kwargs={"site_id": site.id}),
        {"email": manager.email},
    )
    role = SiteRole.objects.get(site=site, user=manager)
    assert add_response.status_code == 302
    assert role.role == SiteRole.Role.SITE_MANAGER

    client.force_login(manager)
    assert (
        client.get(reverse("sites:dashboard", kwargs={"site_id": site.id})).status_code
        == 200
    )
    denied = client.post(
        reverse("sites:add_manager", kwargs={"site_id": site.id}),
        {"email": another.email},
    )
    assert denied.status_code == 403
    assert not SiteRole.objects.filter(site=site, user=another).exists()


@pytest.mark.django_db
def test_only_one_active_subscriber_admin_is_allowed_per_site():
    owner = verified_user("owner@example.com")
    second_owner = verified_user("second@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        SiteRole.objects.create(
            site=site,
            user=second_owner,
            role=SiteRole.Role.SUBSCRIBER_ADMIN,
        )


@pytest.mark.django_db
def test_subdomain_resolves_site_and_unknown_platform_subdomain_returns_404(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )

    response = client.get("/", headers={"host": "boot-scooters.localhost"})
    missing = client.get("/", headers={"host": "missing.localhost"})

    assert response.status_code == 200
    assert site.display_name in response.content.decode()
    assert missing.status_code == 404


@pytest.mark.django_db
@override_settings(
    PLATFORM_DOMAIN="gatherhqs.com",
    PLATFORM_CONTROL_HOSTS=("gatherhqs.com", "www.gatherhqs.com"),
    ALLOWED_HOSTS=("gatherhqs.com", ".gatherhqs.com"),
)
def test_gather_hqs_root_and_www_hosts_remain_control_hosts(client):
    root = client.get("/", headers={"host": "gatherhqs.com"})
    www = client.get("/", headers={"host": "www.gatherhqs.com"})

    assert root.status_code == 200
    assert www.status_code == 200
    assert "Gather HQs" in root.content.decode()
