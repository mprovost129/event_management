from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from sites.models import SiteOwnedModel


class Review(SiteOwnedModel):
    class ModerationStatus(models.TextChoices):
        VISIBLE = "visible", "Visible"
        REPORTED = "reported", "Reported"
        HIDDEN = "hidden", "Hidden by platform moderation"

    occurrence = models.ForeignKey(
        "events.EventOccurrence", on_delete=models.CASCADE, related_name="reviews"
    )
    participant = models.OneToOneField(
        "events.Participant", on_delete=models.CASCADE, related_name="review"
    )
    display_name = models.CharField(max_length=205)
    rating = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1), MaxValueValidator(5))
    )
    comment = models.TextField(blank=True, max_length=3000)
    submitted_at = models.DateTimeField(default=timezone.now)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    moderation_status = models.CharField(
        max_length=20,
        choices=ModerationStatus.choices,
        default=ModerationStatus.VISIBLE,
        db_index=True,
    )
    response = models.TextField(blank=True, max_length=3000)
    responded_at = models.DateTimeField(null=True, blank=True)
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_responses",
    )

    class Meta:
        ordering = ("-submitted_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(rating__gte=1, rating__lte=5),
                name="reviews_rating_between_one_and_five",
            )
        ]

    @property
    def is_public(self):
        return (
            self.deleted_at is None
            and self.moderation_status != self.ModerationStatus.HIDDEN
        )

    def clean(self):
        super().clean()
        if self.participant_id:
            if self.participant.site_id != self.site_id:
                raise ValidationError(
                    "The review participant must belong to this site."
                )
            if self.participant.registration.occurrence_id != self.occurrence_id:
                raise ValidationError(
                    "The review must use the participant's occurrence."
                )

    def __str__(self):
        return f"{self.rating}/5 — {self.display_name}"


class ReviewReport(SiteOwnedModel):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="reports")
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_reports",
    )
    reason = models.CharField(max_length=500)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class ReviewModeration(SiteOwnedModel):
    class Action(models.TextChoices):
        HIDDEN = "hidden", "Hidden"
        RESTORED = "restored", "Restored"

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="moderation_history"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    reason = models.CharField(max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="review_moderation_actions",
    )

    class Meta:
        ordering = ("-created_at",)
