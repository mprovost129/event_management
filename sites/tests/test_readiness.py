from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from contacts.models import Contact
from events.models import Event, EventOccurrence, Invitation
from payments.models import ConnectedAccount, TicketType
from sites.models import SiteRole
from sites.readiness import pilot_readiness
from sites.services import create_subscriber_site
from users.models import User


def readiness_fixture(*, visibility=Event.Visibility.PUBLIC):
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
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    event = Event.objects.create(
        site=site,
        title="Friday dance",
        slug="friday-dance",
        status=Event.Status.PUBLISHED,
        visibility=visibility,
    )
    occurrence = EventOccurrence.objects.create(
        site=site,
        event=event,
        starts_at=timezone.now() + timedelta(days=7),
        ends_at=timezone.now() + timedelta(days=7, hours=2),
        timezone=site.timezone,
        venue_name="Community Hall",
        venue_address="100 Main Street",
    )
    contact = Contact.objects.create(
        site=site,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
    )
    return owner, site, occurrence, contact


@pytest.mark.django_db
def test_free_public_event_is_ready_without_connect():
    _, site, occurrence, _ = readiness_fixture()

    readiness = pilot_readiness(site)
    checks = {check["key"]: check for check in readiness["required"]}

    assert readiness["ok"] is True
    assert readiness["occurrence"] == occurrence
    assert readiness["ticketed"] is False
    assert checks["commerce_ready"]["complete"] is True
    assert checks["invitation_path"]["complete"] is True
    assert readiness["recommended_complete"] == 1


@pytest.mark.django_db
def test_paid_invite_only_event_requires_connect_and_a_sent_invitation():
    _, site, occurrence, contact = readiness_fixture(
        visibility=Event.Visibility.INVITE_ONLY
    )
    TicketType.objects.create(
        site=site,
        occurrence=occurrence,
        name="General admission",
        amount_cents=1000,
        currency=site.currency,
        quantity=40,
    )

    readiness = pilot_readiness(site)
    checks = {check["key"]: check["complete"] for check in readiness["required"]}
    assert readiness["ok"] is False
    assert checks["commerce_ready"] is False
    assert checks["invitation_path"] is False

    ConnectedAccount.objects.create(
        site=site,
        stripe_account_id="acct_ready",
        status=ConnectedAccount.Status.READY,
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    Invitation.objects.create(
        site=site,
        occurrence=occurrence,
        contact=contact,
        token_hash="a" * 64,
        sent_at=timezone.now(),
        expires_at=occurrence.ends_at,
    )

    # A paid event still is not launch-ready until buyers can be told the
    # refund terms before they pay.
    without_policy = pilot_readiness(site)
    site.default_refund_policy = "Full refunds up to 48 hours before the event."
    site.save(update_fields=("default_refund_policy", "updated_at"))

    assert without_policy["ok"] is False
    assert (
        next(
            check
            for check in without_policy["required"]
            if check["key"] == "refund_policy"
        )["complete"]
        is False
    )
    assert pilot_readiness(site)["ok"] is True


@pytest.mark.django_db
def test_launch_center_is_owner_only_and_links_to_next_actions(client):
    owner, site, occurrence, _ = readiness_fixture(
        visibility=Event.Visibility.INVITE_ONLY
    )
    manager = User.objects.create_user(
        email="manager@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    SiteRole.objects.create(
        site=site,
        user=manager,
        role=SiteRole.Role.SITE_MANAGER,
        invited_by=owner,
    )
    url = reverse("sites:launch_center", kwargs={"site_id": site.id})

    client.force_login(manager)
    assert client.get(url).status_code == 403

    client.force_login(owner)
    response = client.get(url)
    content = response.content.decode()
    assert response.status_code == 200
    assert "Pilot launch center" in content
    assert "First invitation sent" in content
    assert (
        reverse(
            "events:invite",
            kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
        )
        in content
    )
    assert "Rehearse before event day" in content
