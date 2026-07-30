from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from attendance.services import set_check_in
from contacts.models import Contact
from events.models import Event, EventOccurrence, Participant, Registration
from ops.models import AuditEvent, SiteDeletionRequest
from ops.services import (
    active_support_grant,
    approve_site_deletion,
    cancel_site_deletion,
    execute_site_deletion,
    grant_support_access,
    request_site_deletion,
)
from payments.models import Order
from reviews.services import save_review
from sites.models import SiteRole
from sites.reporting import event_comparison, site_summary
from sites.services import create_subscriber_site
from users.models import User


def operations_fixture():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    end = timezone.now() - timedelta(hours=1)
    event = Event.objects.create(
        site=site,
        title="Friday dance",
        slug="friday-dance",
        status=Event.Status.PUBLISHED,
    )
    occurrence = EventOccurrence.objects.create(
        site=site,
        event=event,
        starts_at=end - timedelta(hours=2),
        ends_at=end,
        timezone=site.timezone,
        capacity=20,
    )
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    registration = Registration.objects.create(
        site=site,
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        source=Registration.Source.MANAGER,
    )
    participant = Participant.objects.create(
        site=site,
        registration=registration,
        first_name="Alex",
        last_name="Dancer",
        email=contact.email,
        is_primary=True,
    )
    set_check_in(participant=participant, actor=owner, checked_in=True)
    save_review(participant=participant, rating=4, comment="Good event")
    return owner, site, event


@pytest.mark.django_db
def test_summary_and_event_comparison_reconcile_to_fixture():
    _, site, event = operations_fixture()
    summary = site_summary(site)
    comparison = event_comparison(site)

    assert summary["registrations"] == 1
    assert summary["participants"] == 1
    assert summary["checked_in"] == 1
    assert summary["no_show_rate"] == 0
    assert summary["review_count"] == 1
    assert summary["rating_average"] == 4
    assert comparison[0]["event"] == event
    assert comparison[0]["registrations"] == 1
    assert comparison[0]["checked_in"] == 1
    assert comparison[0]["rating_average"] == 4


@pytest.mark.django_db
def test_data_export_is_subscriber_admin_only_and_audited():
    owner, site, _ = operations_fixture()
    manager = User.objects.create_user(
        email="manager@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    SiteRole.objects.create(site=site, user=manager, role=SiteRole.Role.SITE_MANAGER)
    url = reverse("sites:export_data", kwargs={"site_id": site.id})
    client = Client()
    client.force_login(manager)
    assert client.get(url).status_code == 403

    client.force_login(owner)
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Disposition"].endswith('boot-scooters-export.json"')
    assert response.json()["format"] == "gather-hqs-site-export-v1"
    assert len(response.json()["participants"]) == 1
    assert AuditEvent.objects.filter(action="site.data_exported", actor=owner).exists()


@pytest.mark.django_db
def test_support_access_is_explicit_expiring_read_only_and_audited():
    _, site, _ = operations_fixture()
    admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    grant = grant_support_access(
        site=site, actor=admin, reason="Investigate failed delivery"
    )
    assert active_support_grant(site=site, actor=admin) == grant

    client = Client()
    client.force_login(admin)
    response = client.get(reverse("ops:support_snapshot", kwargs={"site_id": site.id}))
    assert response.status_code == 200
    assert b"Read-only support access" in response.content
    assert AuditEvent.objects.filter(action="support.site_viewed", actor=admin).exists()

    grant.expires_at = timezone.now() - timedelta(seconds=1)
    grant.save(update_fields=("expires_at",))
    response = client.get(reverse("ops:support_snapshot", kwargs={"site_id": site.id}))
    assert response.status_code == 302


@pytest.mark.django_db
@override_settings(SUSPENDED_DATA_RETENTION_DAYS=90)
def test_deletion_requires_distinct_admin_and_retention_period():
    _, site, _ = operations_fixture()
    first = User.objects.create_superuser(
        email="first@example.com", password="Strong-Test-Pass-2026!"
    )
    second = User.objects.create_superuser(
        email="second@example.com", password="Strong-Test-Pass-2026!"
    )
    with pytest.raises(ValidationError, match="Suspend"):
        request_site_deletion(site=site, actor=first, reason="Subscriber request")
    site.status = site.Status.SUSPENDED
    site.save(update_fields=("status", "updated_at"))
    deletion = request_site_deletion(
        site=site, actor=first, reason="Subscriber request"
    )

    with pytest.raises(ValidationError, match="different"):
        approve_site_deletion(deletion=deletion, actor=first)
    approved = approve_site_deletion(deletion=deletion, actor=second)
    assert approved.status == SiteDeletionRequest.Status.APPROVED
    assert approved.approved_by == second
    assert approved.deletion_eligible_at >= timezone.now() + timedelta(days=89)
    canceled = cancel_site_deletion(
        deletion=approved, actor=first, reason="Subscriber changed their mind"
    )
    assert canceled.status == SiteDeletionRequest.Status.CANCELED
    assert AuditEvent.objects.filter(
        action="site.deletion_canceled", site_id=site.id
    ).exists()


@pytest.mark.django_db
@override_settings(SUSPENDED_DATA_RETENTION_DAYS=0)
def test_separately_approved_retained_site_can_be_deleted():
    _, site, event = operations_fixture()
    site_id = site.id
    registration = Registration.objects.get(occurrence__event=event)
    Order.objects.create(
        site=site,
        occurrence=registration.occurrence,
        registration=registration,
        purchaser=registration.contact,
        connected_account_id="acct_test",
        currency="usd",
        subtotal_cents=2000,
        total_cents=2000,
        status=Order.Status.PAID,
    )
    site.status = site.Status.SUSPENDED
    site.save(update_fields=("status", "updated_at"))
    first = User.objects.create_superuser(
        email="first@example.com", password="Strong-Test-Pass-2026!"
    )
    second = User.objects.create_superuser(
        email="second@example.com", password="Strong-Test-Pass-2026!"
    )
    deletion = request_site_deletion(
        site=site, actor=first, reason="Subscriber request"
    )
    deletion = approve_site_deletion(deletion=deletion, actor=second)

    completed = execute_site_deletion(deletion=deletion)

    assert completed.status == SiteDeletionRequest.Status.COMPLETED
    assert completed.site is None
    assert completed.site_id_snapshot == site_id


@pytest.mark.django_db
def test_platform_operations_reject_non_admin_and_suspend_with_reason():
    owner, site, _ = operations_fixture()
    client = Client()
    client.force_login(owner)
    assert client.get(reverse("ops:dashboard")).status_code == 403

    admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    client.force_login(admin)
    suspend_url = reverse("ops:suspend_site", kwargs={"site_id": site.id})
    client.post(suspend_url, {"reason": "Terms review"})
    site.refresh_from_db()
    assert site.status == site.Status.SUSPENDED
    assert AuditEvent.objects.filter(
        action="platform.site_suspended", site_id=site.id
    ).exists()


@pytest.mark.django_db
def test_platform_operations_reports_collected_and_returned_ticket_fees():
    _, site, _ = operations_fixture()
    registration = Registration.objects.get(site=site)
    Order.objects.create(
        site=site,
        occurrence=registration.occurrence,
        registration=registration,
        purchaser=registration.contact,
        connected_account_id="acct_test",
        currency=site.currency,
        subtotal_cents=2000,
        total_cents=2000,
        refunded_cents=500,
        application_fee_bps=300,
        application_fee_cents=60,
        application_fee_refunded_cents=15,
        status=Order.Status.PARTIALLY_REFUNDED,
    )
    admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    client = Client()
    client.force_login(admin)

    response = client.get(reverse("ops:dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Net Gather HQs fees" in content
    assert "$0.45" in content
    assert "Across 1 paid order" in content
