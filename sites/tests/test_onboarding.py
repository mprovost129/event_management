from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from contacts.models import Contact
from events.models import Event
from ops.models import AuditEvent
from payments.models import ConnectedAccount
from sites.models import Site, SiteDomain, SiteRole, SiteTheme
from sites.services import create_subscriber_site, site_setup_progress
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
def test_onboarding_explains_site_address_and_subscription_boundary(client, settings):
    owner = verified_user("owner@example.com")
    client.force_login(owner)

    response = client.get(reverse("sites:onboarding"))
    content = response.content.decode()

    assert response.status_code == 200
    assert f".{settings.PLATFORM_DOMAIN}" in content
    assert "One website is included with each subscription" in content
    assert "Create my site and start trial" in content


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
def test_subscriber_dashboard_offers_monthly_and_yearly_standard_billing(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    client.force_login(owner)

    response = client.get(reverse("sites:dashboard", kwargs={"site_id": site.id}))
    content = response.content.decode()

    assert response.status_code == 200
    assert "$20.00" in content
    assert "$220.00" in content
    assert 'name="billing_interval" value="monthly"' in content
    assert 'name="billing_interval" value="yearly"' in content
    assert "Save $20.00 per year" in content
    assert "Your headquarters is 0% ready" in content
    assert "Next: Publish your website" in content


@pytest.mark.django_db
def test_setup_progress_tracks_pilot_launch_essentials():
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    assert site_setup_progress(site)["completed"] == 0

    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    Event.objects.create(
        site=site,
        title="Friday dance",
        slug="friday-dance",
        status=Event.Status.PUBLISHED,
    )
    Contact.objects.create(
        site=site,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
    )
    ConnectedAccount.objects.create(
        site=site,
        stripe_account_id="acct_ready",
        status=ConnectedAccount.Status.READY,
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    subscription = site.platform_subscription
    subscription.stripe_customer_id = "cus_ready"
    subscription.stripe_subscription_id = "sub_ready"
    subscription.billing_interval = PlatformSubscription.BillingInterval.MONTHLY
    subscription.save()

    progress = site_setup_progress(site)
    assert progress["completed"] == progress["total"] == 5
    assert progress["percent"] == 100
    assert progress["next"] is None


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
def test_public_site_shows_dashboard_link_only_to_its_staff(client):
    owner = verified_user("owner@example.com")
    outsider = verified_user("outsider@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    dashboard_url = reverse("sites:dashboard", args=(site.id,))

    client.force_login(owner)
    owner_view = client.get("/", headers={"host": "boot-scooters.localhost"})
    client.force_login(outsider)
    outsider_view = client.get("/", headers={"host": "boot-scooters.localhost"})
    client.logout()
    anonymous_view = client.get("/", headers={"host": "boot-scooters.localhost"})

    assert owner_view.status_code == 200
    assert dashboard_url in owner_view.content.decode()
    assert "Back to dashboard" in owner_view.content.decode()
    assert "Back to dashboard" not in outsider_view.content.decode()
    assert "Back to dashboard" not in anonymous_view.content.decode()


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


@pytest.mark.django_db
def test_suspended_site_exposes_only_owner_recovery_routes(client):
    owner = verified_user("owner@example.com")
    manager = verified_user("manager@example.com")
    other_owner = verified_user("other-owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    active_site = create_subscriber_site(
        owner=other_owner,
        display_name="Active Dancers",
        slug="active-dancers",
        timezone_name="America/New_York",
    )
    SiteRole.objects.create(site=site, user=manager, role=SiteRole.Role.SITE_MANAGER)
    SiteRole.objects.create(
        site=active_site, user=manager, role=SiteRole.Role.SITE_MANAGER
    )
    site.status = Site.Status.SUSPENDED
    site.save(update_fields=("status", "updated_at"))

    client.force_login(owner)
    recovery_dashboard = client.get(
        reverse("sites:dashboard", kwargs={"site_id": site.id})
    )
    assert recovery_dashboard.status_code == 200
    recovery_content = recovery_dashboard.content.decode()
    assert "Owner recovery" in recovery_content
    assert "Everything for your group" not in recovery_content
    assert "Site managers" not in recovery_content
    assert (
        client.get(
            reverse("sites:export_data", kwargs={"site_id": site.id})
        ).status_code
        == 200
    )
    assert (
        client.get(reverse("sites:reports", kwargs={"site_id": site.id})).status_code
        == 403
    )
    assert (
        client.post(
            reverse("sites:add_manager", kwargs={"site_id": site.id}),
            {"email": manager.email},
        ).status_code
        == 403
    )

    client.force_login(manager)
    assert (
        client.get(reverse("sites:dashboard", kwargs={"site_id": site.id})).status_code
        == 403
    )
    assert (
        client.get(
            reverse("sites:dashboard", kwargs={"site_id": active_site.id})
        ).status_code
        == 200
    )
