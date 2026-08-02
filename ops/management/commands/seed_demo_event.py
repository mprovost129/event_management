import calendar
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from events.models import Event, EventOccurrence
from events.services import create_event_series, occurrence_starts
from ops.services import record_audit_event
from payments.models import TicketType
from sites.models import Site

DEMO_EVENT_SLUG = "getting-started-gather-hqs"
DEMO_EVENT_TITLE = "Getting started with Gather HQs"
DEMO_EVENT_DESCRIPTION = (
    "A 30-minute walkthrough of website setup, event publishing, RSVP flow, "
    "and best practices for your first month."
)
DEMO_EVENT_HOST = "Gather HQs"
DEMO_EVENT_VENUE = "Live online session"
DEMO_EVENT_ADDRESS = "Hosted virtually"
DEMO_TICKET_NAME = "Paid demo ticket"
MIN_TICKET_AMOUNT_CENTS = 50


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def next_demo_start(site_timezone, hour, minute):
    now_local = timezone.now().astimezone(ZoneInfo(site_timezone))
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while candidate <= now_local + timedelta(days=2):
        candidate += timedelta(days=7)
    return candidate


def materialize_missing_occurrences(event, start_local, end_local):
    existing_starts = set(event.occurrences.values_list("starts_at", flat=True))
    anchor = (
        event.occurrences.order_by("starts_at").values_list("starts_at", flat=True).first()
        or start_local
    )
    duration = (
        event.occurrences.order_by("starts_at")
        .values_list("ends_at", "starts_at")
        .first()
    )
    if duration:
        event_duration = duration[0] - duration[1]
    else:
        event_duration = end_local - start_local

    created_count = 0
    for starts_at in occurrence_starts(
        anchor,
        event.recurrence,
        event.recurrence_interval,
        event.recurrence_until,
    ):
        if starts_at in existing_starts:
            continue
        EventOccurrence.objects.create(
            site=event.site,
            event=event,
            starts_at=starts_at,
            ends_at=starts_at + event_duration,
            timezone=event.site.timezone,
            venue_name=DEMO_EVENT_VENUE,
            venue_address=DEMO_EVENT_ADDRESS,
            status=EventOccurrence.Status.SCHEDULED,
        )
        created_count += 1
    return created_count


class Command(BaseCommand):
    help = (
        "Create or refresh a recurring public demo/training event for a site, "
        "optionally with a paid demo ticket."
    )

    def add_arguments(self, parser):
        parser.add_argument("site_slug")
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--start-hour", type=int, default=18)
        parser.add_argument("--start-minute", type=int, default=0)
        parser.add_argument("--duration-minutes", type=int, default=30)
        parser.add_argument("--with-paid-ticket", action="store_true")
        parser.add_argument("--ticket-amount-cents", type=int, default=500)
        parser.add_argument("--ticket-quantity", type=int, default=50)

    @transaction.atomic
    def handle(self, *args, **options):
        site = Site.objects.filter(slug=options["site_slug"]).first()
        if site is None:
            raise CommandError("Site not found.")
        if options["months"] < 1:
            raise CommandError("--months must be at least 1.")
        if not 0 <= options["start_hour"] <= 23:
            raise CommandError("--start-hour must be between 0 and 23.")
        if not 0 <= options["start_minute"] <= 59:
            raise CommandError("--start-minute must be between 0 and 59.")
        if options["duration_minutes"] < 15:
            raise CommandError("--duration-minutes must be at least 15.")
        if options["with_paid_ticket"] and options["ticket_amount_cents"] < MIN_TICKET_AMOUNT_CENTS:
            raise CommandError(
                f"--ticket-amount-cents must be at least {MIN_TICKET_AMOUNT_CENTS}."
            )
        if options["with_paid_ticket"] and options["ticket_quantity"] < 1:
            raise CommandError("--ticket-quantity must be at least 1.")

        start_local = next_demo_start(
            site.timezone,
            options["start_hour"],
            options["start_minute"],
        )
        end_local = start_local + timedelta(minutes=options["duration_minutes"])
        recurrence_until = add_months(start_local, options["months"]).date()

        event = Event.objects.for_site(site).filter(slug=DEMO_EVENT_SLUG).first()
        created = False
        if event is None:
            event = create_event_series(
                site=site,
                creator=None,
                event_values={
                    "title": DEMO_EVENT_TITLE,
                    "slug": DEMO_EVENT_SLUG,
                    "description": DEMO_EVENT_DESCRIPTION,
                    "host_name": DEMO_EVENT_HOST,
                    "visibility": Event.Visibility.PUBLIC,
                    "status": Event.Status.PUBLISHED,
                    "recurrence": Event.Recurrence.MONTHLY,
                    "recurrence_interval": 1,
                    "recurrence_until": recurrence_until,
                    "max_guests": 0,
                },
                first_start=start_local,
                first_end=end_local,
                venue_name=DEMO_EVENT_VENUE,
                venue_address=DEMO_EVENT_ADDRESS,
                capacity=None,
            )
            created = True
        else:
            event.title = DEMO_EVENT_TITLE
            event.description = DEMO_EVENT_DESCRIPTION
            event.host_name = DEMO_EVENT_HOST
            event.visibility = Event.Visibility.PUBLIC
            event.status = Event.Status.PUBLISHED
            event.recurrence = Event.Recurrence.MONTHLY
            event.recurrence_interval = 1
            if not event.recurrence_until or event.recurrence_until < recurrence_until:
                event.recurrence_until = recurrence_until
            event.save(
                update_fields=(
                    "title",
                    "description",
                    "host_name",
                    "visibility",
                    "status",
                    "recurrence",
                    "recurrence_interval",
                    "recurrence_until",
                    "updated_at",
                )
            )
            materialize_missing_occurrences(event, start_local, end_local)

        if not site.is_published:
            site.is_published = True
            site.save(update_fields=("is_published", "updated_at"))

        paid_ticket_created = False
        if options["with_paid_ticket"]:
            paid_occurrence = event.occurrences.filter(
                status=EventOccurrence.Status.SCHEDULED,
                ends_at__gte=timezone.now(),
            ).order_by("starts_at").first()
            if paid_occurrence is None:
                raise CommandError("No future occurrence is available for a paid ticket.")
            ticket, paid_ticket_created = TicketType.objects.update_or_create(
                site=site,
                occurrence=paid_occurrence,
                name=DEMO_TICKET_NAME,
                defaults={
                    "description": "A low-cost demo ticket that validates checkout flow.",
                    "amount_cents": options["ticket_amount_cents"],
                    "currency": site.currency,
                    "quantity": options["ticket_quantity"],
                    "max_per_order": 2,
                    "is_active": True,
                },
            )
            del ticket

        record_audit_event(
            action="ops.demo_event.seeded",
            site_id=site.id,
            target=event,
            summary={
                "created": created,
                "with_paid_ticket": options["with_paid_ticket"],
                "paid_ticket_created": paid_ticket_created,
                "event_slug": event.slug,
            },
        )

        future_count = event.occurrences.filter(
            status=EventOccurrence.Status.SCHEDULED,
            ends_at__gte=timezone.now(),
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded demo event for {site.slug}: slug={event.slug} future_occurrences={future_count}"
            )
        )
