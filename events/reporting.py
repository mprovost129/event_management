from attendance.models import AttendanceStatus

from .models import Invitation, Participant, Registration


def occurrence_metrics(occurrence):
    registrations = Registration.objects.filter(occurrence=occurrence)
    active_participants = Participant.objects.filter(
        registration__occurrence=occurrence,
        registration__payment_status__in=(
            Registration.PaymentStatus.NOT_REQUIRED,
            Registration.PaymentStatus.PAID,
        ),
        status=Participant.Status.ACTIVE,
    )
    participant_count = active_participants.count()
    capacity_remaining = None
    if occurrence.capacity is not None:
        capacity_remaining = max(0, occurrence.capacity - participant_count)
    return {
        "invited": Invitation.objects.filter(occurrence=occurrence).count(),
        "going": registrations.filter(response=Registration.Response.GOING).count(),
        "maybe": registrations.filter(response=Registration.Response.MAYBE).count(),
        "not_going": registrations.filter(
            response=Registration.Response.NOT_GOING
        ).count(),
        "payment_pending": registrations.filter(
            response=Registration.Response.GOING,
            payment_status=Registration.PaymentStatus.PENDING,
        ).count(),
        "participants": participant_count,
        "guests": active_participants.filter(is_primary=False).count(),
        "checked_in": AttendanceStatus.objects.filter(
            participant__registration__occurrence=occurrence,
            participant__registration__response=Registration.Response.GOING,
            participant__registration__payment_status__in=(
                Registration.PaymentStatus.NOT_REQUIRED,
                Registration.PaymentStatus.PAID,
            ),
            participant__status=Participant.Status.ACTIVE,
            checked_in_at__isnull=False,
        ).count(),
        "capacity_remaining": capacity_remaining,
    }
