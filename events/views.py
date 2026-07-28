from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ops.services import record_audit_event
from sites.permissions import site_staff_required

from .forms import EventDetailsForm, EventForm, OccurrenceEditForm
from .models import Event, EventOccurrence
from .services import create_event_series, update_occurrences_from


def _public_site(request):
    site = getattr(request, "site", None)
    if site is None or not site.accepts_public_traffic or not site.is_published:
        raise Http404("Site not found.")
    return site


@site_staff_required
def manage_events(request, site_id):
    site = request.authorized_site
    events = Event.objects.for_site(site).prefetch_related("occurrences")
    return render(request, "events/manage.html", {"site": site, "events": events})


@site_staff_required
@require_http_methods(["GET", "POST"])
def event_create(request, site_id):
    site = request.authorized_site
    form = EventForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        model_fields = {
            field: form.cleaned_data[field]
            for field in (
                "title",
                "slug",
                "description",
                "host_name",
                "visibility",
                "status",
                "recurrence",
                "recurrence_interval",
                "recurrence_until",
            )
        }
        event = create_event_series(
            site=site,
            creator=request.user,
            event_values=model_fields,
            first_start=form.cleaned_data["starts_at"],
            first_end=form.cleaned_data["ends_at"],
            venue_name=form.cleaned_data["venue_name"],
            venue_address=form.cleaned_data["venue_address"],
            capacity=form.cleaned_data["capacity"],
        )
        record_audit_event(
            action="event.created",
            actor=request.user,
            site_id=site.id,
            target=event,
            summary={
                "visibility": event.visibility,
                "recurrence": event.recurrence,
                "occurrences": event.occurrences.count(),
            },
            request=request,
        )
        messages.success(request, "Event and its calendar occurrences were created.")
        return redirect("events:manage", site_id=site.id)
    return render(request, "events/event_form.html", {"site": site, "form": form})


@site_staff_required
@require_http_methods(["GET", "POST"])
def event_edit(request, site_id, event_id):
    site = request.authorized_site
    event = get_object_or_404(Event.objects.for_site(site), pk=event_id)
    form = EventDetailsForm(request.POST or None, instance=event, site=site)
    if request.method == "POST" and form.is_valid():
        event = form.save()
        record_audit_event(
            action="event.updated",
            actor=request.user,
            site_id=site.id,
            target=event,
            summary={"status": event.status, "visibility": event.visibility},
            request=request,
        )
        messages.success(request, "Event details were saved.")
        return redirect("events:manage", site_id=site.id)
    return render(
        request,
        "events/event_edit.html",
        {"site": site, "event": event, "form": form},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def occurrence_edit(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = OccurrenceEditForm(request.POST or None, instance=occurrence, site=site)
    if request.method == "POST" and form.is_valid():
        values = {
            key: form.cleaned_data[key]
            for key in (
                "starts_at",
                "ends_at",
                "venue_name",
                "venue_address",
                "capacity",
                "status",
            )
        }
        updated = update_occurrences_from(
            occurrence=occurrence,
            scope=form.cleaned_data["scope"],
            values=values,
        )
        record_audit_event(
            action="event.occurrences.updated",
            actor=request.user,
            site_id=site.id,
            target=occurrence.event,
            summary={"scope": form.cleaned_data["scope"], "count": len(updated)},
            request=request,
        )
        messages.success(request, f"{len(updated)} occurrence(s) were updated.")
        return redirect("events:manage", site_id=site.id)
    return render(
        request,
        "events/occurrence_form.html",
        {"site": site, "occurrence": occurrence, "form": form},
    )


def calendar(request):
    site = _public_site(request)
    occurrences = (
        EventOccurrence.objects.for_site(site)
        .filter(
            event__status=Event.Status.PUBLISHED,
            event__visibility=Event.Visibility.PUBLIC,
            status=EventOccurrence.Status.SCHEDULED,
            ends_at__gte=timezone.now(),
        )
        .select_related("event")
    )
    return render(
        request,
        "public/calendar.html",
        {"site": site, "occurrences": occurrences},
    )


def event_detail(request, slug):
    site = _public_site(request)
    event = get_object_or_404(
        Event.objects.for_site(site).filter(
            status=Event.Status.PUBLISHED,
            visibility__in=(Event.Visibility.PUBLIC, Event.Visibility.UNLISTED),
        ),
        slug=slug,
    )
    occurrences = event.occurrences.filter(
        status=EventOccurrence.Status.SCHEDULED, ends_at__gte=timezone.now()
    )
    return render(
        request,
        "public/event_detail.html",
        {"site": site, "event": event, "occurrences": occurrences},
    )


def occurrence_detail(request, slug, occurrence_id):
    site = _public_site(request)
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site)
        .select_related("event")
        .filter(
            event__slug=slug,
            event__status=Event.Status.PUBLISHED,
            event__visibility__in=(
                Event.Visibility.PUBLIC,
                Event.Visibility.UNLISTED,
            ),
            status=EventOccurrence.Status.SCHEDULED,
        ),
        pk=occurrence_id,
    )
    return render(
        request,
        "public/occurrence_detail.html",
        {"site": site, "event": occurrence.event, "occurrence": occurrence},
    )
