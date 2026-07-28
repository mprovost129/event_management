import calendar
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction

from .models import Event, EventOccurrence

MAX_MATERIALIZED_OCCURRENCES = 500


def local_datetime(site, date_value, time_value):
    return datetime.combine(date_value, time_value, tzinfo=ZoneInfo(site.timezone))


def _add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def occurrence_starts(first_start, recurrence, interval, until):
    current = first_start
    count = 0
    while True:
        yield current
        count += 1
        if recurrence == Event.Recurrence.NONE:
            return
        if count >= MAX_MATERIALIZED_OCCURRENCES:
            raise ValueError(
                f"A recurring event cannot exceed {MAX_MATERIALIZED_OCCURRENCES} occurrences."
            )
        if recurrence == Event.Recurrence.WEEKLY:
            current = first_start + timedelta(weeks=interval * count)
        elif recurrence == Event.Recurrence.MONTHLY:
            current = _add_months(first_start, interval * count)
        else:
            current = None
        if current is None or (until and current.date() > until):
            return


@transaction.atomic
def create_event_series(
    *,
    site,
    creator,
    event_values,
    first_start,
    first_end,
    venue_name="",
    venue_address="",
    capacity=None,
):
    event = Event.objects.create(site=site, created_by=creator, **event_values)
    duration = first_end - first_start
    occurrences = [
        EventOccurrence(
            site=site,
            event=event,
            starts_at=start,
            ends_at=start + duration,
            timezone=site.timezone,
            venue_name=venue_name,
            venue_address=venue_address,
            capacity=capacity,
        )
        for start in occurrence_starts(
            first_start,
            event.recurrence,
            event.recurrence_interval,
            event.recurrence_until,
        )
    ]
    EventOccurrence.objects.bulk_create(occurrences)
    return event


@transaction.atomic
def update_occurrences_from(*, occurrence, scope, values):
    original_start = occurrence.starts_at
    new_start = values["starts_at"]
    start_delta = new_start - original_start
    duration = values["ends_at"] - new_start

    occurrences = EventOccurrence.objects.for_site(occurrence.site).filter(
        event=occurrence.event
    )
    if scope == "one":
        occurrences = occurrences.filter(pk=occurrence.pk)
    elif scope == "future":
        occurrences = occurrences.filter(starts_at__gte=original_start)
    elif scope != "all":
        raise ValueError("Occurrence scope must be one, future, or all.")

    updated = []
    for item in occurrences.select_for_update().order_by("starts_at"):
        item.starts_at += start_delta
        item.ends_at = item.starts_at + duration
        item.venue_name = values["venue_name"]
        item.venue_address = values["venue_address"]
        item.capacity = values["capacity"]
        item.status = values["status"]
        updated.append(item)
    EventOccurrence.objects.bulk_update(
        updated,
        (
            "starts_at",
            "ends_at",
            "venue_name",
            "venue_address",
            "capacity",
            "status",
            "updated_at",
        ),
    )
    return updated
