from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from contacts.models import Contact
from events.models import Event, EventAlbum
from events.services import create_event_series
from ops.models import AuditEvent
from payments.models import ConnectedAccount
from sites.models import Site, SiteDomain, SiteRole, SiteTheme
from sites.services import (
    SiteCreationNotAllowed,
    create_subscriber_site,
    site_setup_progress,
)
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
def test_subscriber_cannot_start_another_site_while_a_trial_exists(client):
    owner = verified_user("owner@example.com")
    create_subscriber_site(
        owner=owner,
        display_name="First Organization",
        slug="first-organization",
        timezone_name="America/New_York",
    )
    client.force_login(owner)

    onboarding = client.get(reverse("sites:onboarding"))
    dashboard = client.get(reverse("sites:account_dashboard"))
    blocked_post = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Second Organization",
            "slug": "second-organization",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )

    assert onboarding.status_code == 200
    assert blocked_post.status_code == 403
    assert "already have an organization in its trial" in onboarding.content.decode()
    assert "Create another organization" not in dashboard.content.decode()
    assert Site.objects.count() == 1
    with pytest.raises(SiteCreationNotAllowed):
        create_subscriber_site(
            owner=owner,
            display_name="Service Bypass",
            slug="service-bypass",
            timezone_name="America/New_York",
        )


@pytest.mark.django_db
def test_active_subscriber_can_start_one_additional_trial_but_not_a_third(client):
    owner = verified_user("owner@example.com")
    paid_site = create_subscriber_site(
        owner=owner,
        display_name="Paid Organization",
        slug="paid-organization",
        timezone_name="America/New_York",
    )
    paid_subscription = paid_site.platform_subscription
    paid_subscription.status = PlatformSubscription.Status.ACTIVE
    paid_subscription.save(update_fields=("status", "updated_at"))
    paid_site.status = Site.Status.ACTIVE
    paid_site.save(update_fields=("status", "updated_at"))
    client.force_login(owner)

    dashboard = client.get(reverse("sites:account_dashboard"))
    second_site = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Second Organization",
            "slug": "second-organization",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )
    third_site = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Third Organization",
            "slug": "third-organization",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )

    assert dashboard.status_code == 200
    assert "Create another organization" in dashboard.content.decode()
    assert second_site.status_code == 302
    assert Site.objects.get(
        slug="second-organization"
    ).platform_subscription.status == (PlatformSubscription.Status.TRIALING)
    assert third_site.status_code == 403
    assert not Site.objects.filter(slug="third-organization").exists()


@pytest.mark.django_db
def test_account_dashboard_shows_visit_site_for_published_public_organization(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Published Organization",
        slug="published-organization",
        timezone_name="America/New_York",
    )
    site.is_published = True
    site.status = Site.Status.ACTIVE
    site.save(update_fields=("is_published", "status", "updated_at"))
    client.force_login(owner)

    response = client.get(reverse("sites:account_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Visit site" in content
    assert "//published-organization.localhost" in content


@pytest.mark.django_db
def test_site_dashboard_shows_quick_links_cluster(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Quick Links Organization",
        slug="quick-links-organization",
        timezone_name="America/New_York",
    )
    client.force_login(owner)

    response = client.get(reverse("sites:dashboard", kwargs={"site_id": site.id}))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Quick links" in content
    assert "Reports" in content
    assert "Tasks" in content
    assert "People" in content
    assert "Campaigns" in content


@pytest.mark.django_db
def test_manager_roles_do_not_prevent_a_first_owned_site(client):
    subscriber = verified_user("subscriber@example.com")
    manager = verified_user("manager@example.com")
    managed_site = create_subscriber_site(
        owner=subscriber,
        display_name="Managed Organization",
        slug="managed-organization",
        timezone_name="America/New_York",
    )
    SiteRole.objects.create(
        site=managed_site,
        user=manager,
        role=SiteRole.Role.SITE_MANAGER,
    )
    client.force_login(manager)

    onboarding = client.get(reverse("sites:onboarding"))
    created = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Manager's Organization",
            "slug": "managers-organization",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )

    assert onboarding.status_code == 200
    assert created.status_code == 302
    assert SiteRole.objects.filter(
        site__slug="managers-organization",
        user=manager,
        role=SiteRole.Role.SUBSCRIBER_ADMIN,
    ).exists()


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
def test_quick_start_renders_every_growth_step_route(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    client.force_login(owner)

    response = client.get(reverse("sites:quick_start", kwargs={"site_id": site.id}))
    content = response.content.decode()

    assert response.status_code == 200
    expected_routes = (
        "content:manage",
        "content:blog_create",
        "workspace:task_create",
        "workspace:intake_form_create",
        "workspace:document_upload",
        "workspace:automation_create",
    )
    for route_name in expected_routes:
        assert reverse(route_name, kwargs={"site_id": site.id}) in content


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
    assert "Gather HQs" in root.content.decode()
    # The session/CSRF cookies are host-only (platform.E034/E035), so the
    # "www." alias must funnel onto the canonical host rather than serving
    # the page directly, or a login on one alias is invisible on the other.
    assert www.status_code == 302
    assert www.url == "http://gatherhqs.com/"


@pytest.mark.django_db
@override_settings(
    PLATFORM_DOMAIN="gatherhqs.com",
    PLATFORM_CONTROL_HOSTS=("gatherhqs.com", "www.gatherhqs.com"),
    ALLOWED_HOSTS=("gatherhqs.com", ".gatherhqs.com"),
)
def test_www_redirect_preserves_path_and_leaves_non_get_requests_alone():
    from django.test import Client

    client = Client()
    redirected = client.get(
        "/accounts/login/?next=/dashboard/", headers={"host": "www.gatherhqs.com"}
    )
    posted = client.post(
        "/accounts/login/", headers={"host": "www.gatherhqs.com"}
    )

    assert redirected.status_code == 302
    assert redirected.url == "http://gatherhqs.com/accounts/login/?next=/dashboard/"
    # A server-to-server call (e.g. a webhook) against the alias host must be
    # served directly, never redirected.
    assert posted.status_code != 302


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


@pytest.mark.django_db
def test_account_overview_does_not_dead_end_a_manager_on_a_suspended_site(client):
    owner = verified_user("owner@example.com")
    other_owner = verified_user("other-owner@example.com")
    manager = verified_user("manager@example.com")
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

    client.force_login(manager)
    response = client.get(reverse("sites:account_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "This organization is suspended" in content
    dashboard_url = reverse("sites:dashboard", kwargs={"site_id": site.id})
    assert f'href="{dashboard_url}"' not in content
    active_dashboard_url = reverse(
        "sites:dashboard", kwargs={"site_id": active_site.id}
    )
    assert f'href="{active_dashboard_url}"' in content

    # The owner still gets the clickable recovery link on the same site.
    client.force_login(owner)
    owner_response = client.get(reverse("sites:account_dashboard"))
    assert f'href="{dashboard_url}"' in owner_response.content.decode()


@pytest.mark.django_db
def test_dashboard_prompts_for_photos_after_an_event_finishes(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    client.force_login(owner)
    finished = timezone.now() - timedelta(days=2)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Summer social",
            "slug": "summer-social",
            "description": "",
            "host_name": "Pat",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 0,
        },
        first_start=finished,
        first_end=finished + timedelta(hours=2),
        venue_name="Town Hall",
    )
    occurrence = event.occurrences.get()

    prompted = client.get(reverse("sites:dashboard", kwargs={"site_id": site.id}))

    # Once an album exists for that date, the dashboard stops asking.
    EventAlbum.objects.create(
        site=site,
        occurrence=occurrence,
        title="Summer Social Highlights",
        slug="summer-social-highlights",
        created_by=owner,
    )
    settled = client.get(reverse("sites:dashboard", kwargs={"site_id": site.id}))

    assert "Add photos from Summer social" in prompted.content.decode()
    assert "Add photos from Summer social" not in settled.content.decode()


@pytest.mark.django_db
def test_dashboard_keeps_secondary_tools_collapsed_behind_more_tools(client):
    owner = verified_user("owner@example.com")
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    client.force_login(owner)

    content = client.get(
        reverse("sites:dashboard", kwargs={"site_id": site.id})
    ).content.decode()

    # The core loop stays visible; everything else is one click away.
    assert "Photo albums" in content
    assert "Events &amp; calendar" in content
    assert "gh-more-tools" in content
    assert content.index("gh-more-tools") < content.index("Sponsors")
