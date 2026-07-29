from decimal import Decimal

from django.contrib import messages
from django.db.models import Avg
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from core.rate_limits import public_write_rate_limit
from ops.services import record_audit_event
from payments.services import registration_checkout_token, ticket_inventory
from sites.permissions import site_staff_required

from .forms import (
    EventDetailsForm,
    EventForm,
    InvitationForm,
    ManagerResponseForm,
    OccurrenceEditForm,
    RSVPForm,
)
from .messaging import queue_confirmation, queue_invitation, queue_occurrence_notice
from .models import Event, EventOccurrence, Registration
from .registration import (
    CapacityExceeded,
    RegistrationUnavailable,
    create_invitations,
    invitation_for_token,
    save_public_response,
    save_response,
)
from .reporting import occurrence_metrics
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
    created_event_id = request.GET.get("created", "")
    for event in events:
        event.just_created = str(event.id) == created_event_id
        occurrences = list(event.occurrences.all())
        event.first_occurrence = occurrences[0] if occurrences else None
        for occurrence in occurrences:
            occurrence.metrics = occurrence_metrics(occurrence)
    return render(
        request,
        "events/manage.html",
        {
            "site": site,
            "events": events,
            "canonical_domain": site.domains.filter(is_canonical=True).first(),
        },
    )


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
                "max_guests",
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
        return redirect(
            f"{reverse('events:manage', kwargs={'site_id': site.id})}?created={event.id}"
        )
    return render(request, "events/event_form.html", {"site": site, "form": form})


@site_staff_required
@require_http_methods(["GET", "POST"])
def event_edit(request, site_id, event_id):
    site = request.authorized_site
    event = get_object_or_404(Event.objects.for_site(site), pk=event_id)
    previous = {
        "title": event.title,
        "description": event.description,
        "host_name": event.host_name,
        "visibility": event.visibility,
        "status": event.status,
    }
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
        changed = any(
            getattr(event, field) != value for field, value in previous.items()
        )
        if (
            event.status == Event.Status.CANCELED
            and previous["status"] != Event.Status.CANCELED
        ):
            for occurrence in event.occurrences.exclude(
                status=EventOccurrence.Status.CANCELED
            ):
                occurrence.status = EventOccurrence.Status.CANCELED
                occurrence.save(update_fields=("status", "updated_at"))
                queue_occurrence_notice(occurrence, cancellation=True)
        elif changed and event.status == Event.Status.PUBLISHED:
            for occurrence in event.occurrences.filter(
                status=EventOccurrence.Status.SCHEDULED,
                ends_at__gte=timezone.now(),
            ):
                queue_occurrence_notice(
                    occurrence, revision_key=event.updated_at.isoformat()
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
        if form.cleaned_data["status"] == EventOccurrence.Status.CANCELED:
            for item in updated:
                queue_occurrence_notice(item, cancellation=True)
        else:
            for item in updated:
                queue_occurrence_notice(item)
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


@site_staff_required
@require_http_methods(["GET", "POST"])
def invite_contacts(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = InvitationForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        invitations = create_invitations(
            site=site,
            occurrence=occurrence,
            contacts=form.cleaned_data["contacts"],
            actor=request.user,
        )
        hostname = site.domains.get(is_canonical=True).hostname
        scheme = "https" if request.is_secure() else "http"
        for invitation, token in invitations:
            response_path = reverse(
                "events:invitation_response", kwargs={"token": token}
            )
            queue_invitation(
                invitation=invitation,
                token=token,
                response_url=f"{scheme}://{hostname}{response_path}",
            )
        messages.success(request, f"Queued {len(invitations)} invitation(s).")
        return redirect("events:manage", site_id=site.id)
    return render(
        request,
        "events/invite_form.html",
        {"site": site, "occurrence": occurrence, "form": form},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def manager_response(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = ManagerResponseForm(request.POST or None, site=site, occurrence=occurrence)
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_response(
                occurrence=occurrence,
                contact=form.cleaned_data["contact"],
                response=form.cleaned_data["response"],
                guests=form.guest_data(),
                source=Registration.Source.MANAGER,
                actor=request.user,
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            messages.success(request, "The response was recorded.")
            return redirect(
                "attendance:roster", site_id=site.id, occurrence_id=occurrence.id
            )
    return render(
        request,
        "events/manager_response_form.html",
        {
            "site": site,
            "occurrence": occurrence,
            "form": form,
            "paid_event": form.paid_event,
            "guest_groups": [
                {
                    "number": index,
                    "first_name": form[f"guest_{index}_first_name"],
                    "last_name": form[f"guest_{index}_last_name"],
                    "email": form[f"guest_{index}_email"],
                    "phone": form[f"guest_{index}_phone"],
                }
                for index in range(1, occurrence.event.max_guests + 1)
            ],
        },
    )


@site_staff_required
@require_POST
def cancel_event(request, site_id, event_id):
    site = request.authorized_site
    event = get_object_or_404(Event.objects.for_site(site), pk=event_id)
    event.status = Event.Status.CANCELED
    event.save(update_fields=("status", "updated_at"))
    occurrences = list(
        event.occurrences.exclude(status=EventOccurrence.Status.CANCELED)
    )
    for occurrence in occurrences:
        occurrence.status = EventOccurrence.Status.CANCELED
        occurrence.save(update_fields=("status", "updated_at"))
        queue_occurrence_notice(occurrence, cancellation=True)
    record_audit_event(
        action="event.canceled",
        actor=request.user,
        site_id=site.id,
        target=event,
        summary={"occurrences": len(occurrences)},
        request=request,
    )
    messages.success(request, "The event was canceled and notices were queued.")
    return redirect("events:manage", site_id=site.id)


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
    ticket_types = occurrence.ticket_types.filter(is_active=True)
    for ticket_type in ticket_types:
        ticket_type.price_display = Decimal(ticket_type.amount_cents) / 100
        ticket_type.inventory = ticket_inventory(ticket_type)
        ticket_type.available_now = (
            ticket_type.sales_are_open() and ticket_type.inventory["remaining"] > 0
        )
    public_reviews = occurrence.reviews.filter(deleted_at__isnull=True).exclude(
        moderation_status="hidden"
    )
    rating_summary = public_reviews.aggregate(average=Avg("rating"))
    return render(
        request,
        "public/occurrence_detail.html",
        {
            "site": site,
            "event": occurrence.event,
            "occurrence": occurrence,
            "metrics": occurrence_metrics(occurrence),
            "ticket_types": ticket_types,
            "reviews": public_reviews,
            "review_average": rating_summary["average"],
            "review_count": public_reviews.count(),
        },
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("public-rsvp")
def public_response(request, slug, occurrence_id):
    site = _public_site(request)
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"),
        pk=occurrence_id,
        event__slug=slug,
        event__status=Event.Status.PUBLISHED,
        event__visibility__in=(Event.Visibility.PUBLIC, Event.Visibility.UNLISTED),
        status=EventOccurrence.Status.SCHEDULED,
        ends_at__gte=timezone.now(),
    )
    form = RSVPForm(request.POST or None, occurrence=occurrence)
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_public_response(
                site=site,
                occurrence=occurrence,
                response=form.cleaned_data["response"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                guests=form.guest_data(),
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            return render(
                request,
                "public/rsvp_complete.html",
                {
                    "site": site,
                    "registration": registration,
                    "checkout_token": (
                        registration_checkout_token(registration)
                        if registration.payment_status
                        == Registration.PaymentStatus.PENDING
                        else ""
                    ),
                },
            )
    return render(
        request,
        "public/rsvp_form.html",
        {"site": site, "occurrence": occurrence, "form": form},
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("invitation-rsvp")
def invitation_response(request, token):
    site = _public_site(request)
    invitation = invitation_for_token(site=site, token=token)
    if invitation is None:
        raise Http404("Invitation not found.")
    form = RSVPForm(
        request.POST or None,
        occurrence=invitation.occurrence,
        contact=invitation.contact,
    )
    if request.method == "POST" and form.is_valid():
        try:
            registration, history = save_response(
                occurrence=invitation.occurrence,
                contact=invitation.contact,
                response=form.cleaned_data["response"],
                guests=form.guest_data(),
                source=Registration.Source.INVITATION,
                invitation=invitation,
            )
        except (CapacityExceeded, RegistrationUnavailable) as exc:
            form.add_error(None, str(exc))
        else:
            queue_confirmation(registration, history)
            return render(
                request,
                "public/rsvp_complete.html",
                {
                    "site": site,
                    "registration": registration,
                    "checkout_token": (
                        registration_checkout_token(registration)
                        if registration.payment_status
                        == Registration.PaymentStatus.PENDING
                        else ""
                    ),
                },
            )
    return render(
        request,
        "public/invitation_response.html",
        {"site": site, "invitation": invitation, "form": form},
    )
