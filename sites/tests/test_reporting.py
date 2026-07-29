from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from attendance.services import set_check_in
from contacts.models import Contact
from events.models import Event, Registration
from events.registration import save_response
from events.services import create_event_series
from payments.models import Order, TicketType
from reviews.models import Review
from sites.reporting import occurrence_comparison
from sites.services import create_subscriber_site
from users.models import User


def create_site_with_past_event(*, owner, slug, title):
    site = create_subscriber_site(
        owner=owner,
        display_name=title,
        slug=slug,
        timezone_name="America/New_York",
    )
    starts_at = timezone.now() - timedelta(days=2)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": title,
            "slug": slug,
            "description": "",
            "host_name": title,
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 1,
        },
        first_start=starts_at,
        first_end=starts_at + timedelta(hours=2),
        capacity=40,
    )
    return site, event.occurrences.get()


@pytest.mark.django_db
def test_occurrence_comparison_keeps_date_metrics_accurate_and_tenant_scoped():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site, occurrence = create_site_with_past_event(
        owner=owner, slug="past-dance", title="Past dance"
    )
    other_owner = User.objects.create_user(
        email="other@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    create_site_with_past_event(
        owner=other_owner, slug="other-dance", title="Other dance"
    )
    contact = Contact.objects.create(
        site=site,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
    )
    registration, _ = save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        guests=[{"first_name": "Sam", "last_name": "Guest"}],
        source=Registration.Source.MANAGER,
    )
    primary = registration.participants.get(is_primary=True)
    set_check_in(participant=primary, actor=owner, checked_in=True)
    TicketType.objects.create(
        site=site,
        occurrence=occurrence,
        name="Admission",
        amount_cents=2500,
        currency=site.currency,
        quantity=100,
    )
    pending_contact = Contact.objects.create(
        site=site,
        first_name="Taylor",
        last_name="Pending",
        email="taylor@example.com",
    )
    save_response(
        occurrence=occurrence,
        contact=pending_contact,
        response=Registration.Response.GOING,
        guests=[],
        source=Registration.Source.MANAGER,
    )
    Order.objects.create(
        site=site,
        occurrence=occurrence,
        registration=registration,
        purchaser=contact,
        connected_account_id="acct_test",
        currency=site.currency,
        subtotal_cents=2500,
        total_cents=2500,
        refunded_cents=500,
        stripe_fee_cents=100,
        status=Order.Status.PARTIALLY_REFUNDED,
    )
    Review.objects.create(
        site=site,
        occurrence=occurrence,
        participant=primary,
        display_name="Alex D.",
        rating=4,
    )

    rows = occurrence_comparison(site)

    assert len(rows) == 1
    assert rows[0]["occurrence"] == occurrence
    assert rows[0]["registrations"] == 2
    assert rows[0]["participants"] == 2
    assert rows[0]["guests"] == 1
    assert rows[0]["payment_pending"] == 1
    assert rows[0]["checked_in"] == 1
    assert rows[0]["attendance_rate"] == 50.0
    assert rows[0]["net_display"] == 19
    assert rows[0]["rating_average"] == 4
    assert rows[0]["is_complete"] is True


@pytest.mark.django_db
def test_reports_page_filters_event_dates_without_crossing_tenants(client):
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site, _ = create_site_with_past_event(
        owner=owner, slug="past-dance", title="Past dance"
    )
    other_owner = User.objects.create_user(
        email="other@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    create_site_with_past_event(
        owner=other_owner, slug="other-dance", title="Other dance"
    )
    client.force_login(owner)

    completed = client.get(
        reverse("sites:reports", kwargs={"site_id": site.id}), {"view": "completed"}
    )
    upcoming = client.get(
        reverse("sites:reports", kwargs={"site_id": site.id}), {"view": "upcoming"}
    )

    assert completed.status_code == 200
    assert "Past dance" in completed.content.decode()
    assert "Other dance" not in completed.content.decode()
    assert "No event dates in this view" in upcoming.content.decode()
