from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from events.models import Participant, Registration

from .models import AttendanceRecord, AttendanceStatus


@transaction.atomic
def set_check_in(*, participant, actor, checked_in, note=""):
    participant = (
        Participant.objects.select_for_update()
        .select_related("registration__occurrence")
        .get(pk=participant.pk)
    )
    if (
        participant.status != Participant.Status.ACTIVE
        or participant.registration.response != Registration.Response.GOING
    ):
        raise ValidationError("Only active going participants can be checked in.")
    status, _ = AttendanceStatus.objects.select_for_update().get_or_create(
        site=participant.site, participant=participant
    )
    currently_checked_in = status.checked_in_at is not None
    if currently_checked_in == checked_in:
        return status, None

    action = (
        AttendanceRecord.Action.CHECKED_IN
        if checked_in
        else AttendanceRecord.Action.UNDONE
    )
    status.checked_in_at = timezone.now() if checked_in else None
    status.checked_in_by = actor if checked_in else None
    status.save(update_fields=("checked_in_at", "checked_in_by", "updated_at"))
    record = AttendanceRecord.objects.create(
        site=participant.site,
        participant=participant,
        occurrence=participant.registration.occurrence,
        action=action,
        actor=actor,
        note=note[:300],
    )
    return status, record
