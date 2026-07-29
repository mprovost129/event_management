from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from events.models import EventOccurrence, Participant, Registration
from events.reporting import occurrence_metrics
from ops.services import record_audit_event
from sites.permissions import site_staff_required

from .services import set_check_in


@site_staff_required
def roster(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    participants = (
        Participant.objects.for_site(site)
        .filter(
            registration__occurrence=occurrence,
            registration__response=Registration.Response.GOING,
            registration__payment_status__in=(
                Registration.PaymentStatus.NOT_REQUIRED,
                Registration.PaymentStatus.PAID,
            ),
            status=Participant.Status.ACTIVE,
        )
        .select_related(
            "registration__contact",
            "registration__contact__membership",
            "attendance_status",
            "ticket",
        )
    )
    query = request.GET.get("q", "").strip()
    check_in_filter = request.GET.get("status", "all")
    party_filter = request.GET.get("party", "all")
    if query:
        participants = participants.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    if check_in_filter == "checked_in":
        participants = participants.filter(
            attendance_status__checked_in_at__isnull=False
        )
    elif check_in_filter == "not_checked_in":
        participants = participants.filter(
            Q(attendance_status__isnull=True)
            | Q(attendance_status__checked_in_at__isnull=True)
        )
    else:
        check_in_filter = "all"
    if party_filter == "attendees":
        participants = participants.filter(is_primary=True)
    elif party_filter == "guests":
        participants = participants.filter(is_primary=False)
    else:
        party_filter = "all"
    pending_registrations = (
        Registration.objects.for_site(site)
        .filter(
            occurrence=occurrence,
            response=Registration.Response.GOING,
            payment_status=Registration.PaymentStatus.PENDING,
        )
        .select_related("contact")
        .annotate(
            party_size=Count(
                "participants",
                filter=Q(participants__status=Participant.Status.ACTIVE),
            )
        )
    )
    return render(
        request,
        "attendance/roster.html",
        {
            "site": site,
            "occurrence": occurrence,
            "participants": participants,
            "metrics": occurrence_metrics(occurrence),
            "query": query,
            "check_in_filter": check_in_filter,
            "party_filter": party_filter,
            "pending_registrations": pending_registrations,
        },
    )


@site_staff_required
@require_POST
def toggle_check_in(request, site_id, occurrence_id, participant_id):
    site = request.authorized_site
    participant = get_object_or_404(
        Participant.objects.for_site(site).filter(
            registration__occurrence_id=occurrence_id
        ),
        pk=participant_id,
    )
    checked_in = request.POST.get("action") == "check_in"
    try:
        _, record = set_check_in(
            participant=participant,
            actor=request.user,
            checked_in=checked_in,
            note=request.POST.get("note", ""),
        )
    except ValidationError as exc:
        messages.error(request, exc.message)
    else:
        if record is not None:
            record_audit_event(
                action=f"attendance.{record.action}",
                actor=request.user,
                site_id=site.id,
                target=participant,
                summary={
                    "participant_id": str(participant.id),
                    "occurrence_id": str(occurrence_id),
                },
                request=request,
            )
        messages.success(
            request, "Check-in recorded." if checked_in else "Check-in was undone."
        )
    roster_url = reverse("attendance:roster", args=(site.id, occurrence_id))
    return_params = {}
    query = request.POST.get("q", "").strip()
    status = request.POST.get("status", "")
    party = request.POST.get("party", "")
    if query:
        return_params["q"] = query
    if status in {"checked_in", "not_checked_in"}:
        return_params["status"] = status
    if party in {"attendees", "guests"}:
        return_params["party"] = party
    if return_params:
        roster_url = f"{roster_url}?{urlencode(return_params)}"
    return redirect(roster_url)
