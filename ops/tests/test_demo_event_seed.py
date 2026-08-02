from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from events.models import Event, EventOccurrence
from ops.models import AuditEvent
from payments.models import TicketType
from sites.services import create_subscriber_site
from users.models import User


def create_site(slug="boot-scooters"):
    owner = User.objects.create_user(
        email=f"{slug}@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug=slug,
        timezone_name="America/New_York",
    )
    return owner, site


@pytest.mark.django_db
def test_seed_demo_event_creates_public_recurring_event_and_audit_record():
    _, site = create_site()

    call_command("seed_demo_event", site.slug)
    site.refresh_from_db()

    event = Event.objects.get(site=site, slug="getting-started-gather-hqs")
    future_occurrences = event.occurrences.filter(
        status=EventOccurrence.Status.SCHEDULED,
        ends_at__gte=timezone.now(),
    )

    assert event.status == Event.Status.PUBLISHED
    assert event.visibility == Event.Visibility.PUBLIC
    assert event.recurrence == Event.Recurrence.MONTHLY
    assert future_occurrences.exists()
    assert site.is_published is True
    assert AuditEvent.objects.filter(
        site_id=site.id,
        action="ops.demo_event.seeded",
    ).exists()


@pytest.mark.django_db
def test_seed_demo_event_with_paid_ticket_is_idempotent():
    _, site = create_site()

    call_command("seed_demo_event", site.slug, with_paid_ticket=True)
    call_command("seed_demo_event", site.slug, with_paid_ticket=True)

    event = Event.objects.get(site=site, slug="getting-started-gather-hqs")
    assert Event.objects.filter(site=site, slug="getting-started-gather-hqs").count() == 1

    future_occurrence = event.occurrences.filter(
        status=EventOccurrence.Status.SCHEDULED,
        ends_at__gte=timezone.now() - timedelta(minutes=1),
    ).order_by("starts_at").first()
    assert future_occurrence is not None

    tickets = TicketType.objects.filter(
        site=site,
        occurrence=future_occurrence,
        name="Paid demo ticket",
    )
    assert tickets.count() == 1
    ticket = tickets.get()
    assert ticket.amount_cents == 500
    assert ticket.quantity == 50


@pytest.mark.django_db
def test_seed_demo_event_rematerializes_missing_future_occurrences():
    _, site = create_site("rematerialize-site")

    call_command("seed_demo_event", site.slug, months=3)
    event = Event.objects.get(site=site, slug="getting-started-gather-hqs")
    event.occurrences.all().delete()

    call_command("seed_demo_event", site.slug, months=6)
    event.refresh_from_db()

    future_occurrence_count = event.occurrences.filter(
        status=EventOccurrence.Status.SCHEDULED,
        ends_at__gte=timezone.now(),
    ).count()
    assert future_occurrence_count >= 6


@pytest.mark.django_db
def test_seed_demo_event_rejects_invalid_paid_ticket_inputs():
    _, site = create_site("invalid-ticket-site")

    with pytest.raises(CommandError, match="--ticket-amount-cents must be at least 50"):
        call_command(
            "seed_demo_event",
            site.slug,
            with_paid_ticket=True,
            ticket_amount_cents=10,
        )

    with pytest.raises(CommandError, match="--ticket-quantity must be at least 1"):
        call_command(
            "seed_demo_event",
            site.slug,
            with_paid_ticket=True,
            ticket_quantity=0,
        )
