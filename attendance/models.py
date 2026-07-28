from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from sites.models import SiteOwnedModel


class AttendanceStatus(SiteOwnedModel):
    participant = models.OneToOneField(
        "events.Participant",
        on_delete=models.CASCADE,
        related_name="attendance_status",
    )
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_in_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="current_check_ins",
    )

    def clean(self):
        super().clean()
        if self.participant_id and self.site_id != self.participant.site_id:
            raise ValidationError(
                "Attendance status must belong to the participant's site."
            )

    def __str__(self):
        return f"Attendance for {self.participant}"


class AttendanceRecord(SiteOwnedModel):
    class Action(models.TextChoices):
        CHECKED_IN = "checked_in", "Checked in"
        UNDONE = "undone", "Check-in undone"

    participant = models.ForeignKey(
        "events.Participant",
        on_delete=models.CASCADE,
        related_name="attendance_history",
    )
    occurrence = models.ForeignKey(
        "events.EventOccurrence",
        on_delete=models.CASCADE,
        related_name="attendance_history",
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendance_actions",
    )
    note = models.CharField(max_length=300, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-recorded_at",)

    def clean(self):
        super().clean()
        if self.participant_id:
            if self.site_id != self.participant.site_id:
                raise ValidationError(
                    "Attendance history must belong to the participant's site."
                )
            if self.occurrence_id != self.participant.registration.occurrence_id:
                raise ValidationError(
                    "Attendance history must use the participant's occurrence."
                )

    def __str__(self):
        return f"{self.get_action_display()}: {self.participant}"
