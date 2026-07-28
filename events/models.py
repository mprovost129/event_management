from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q

from sites.models import SiteOwnedModel
from sites.validators import validate_timezone


class Event(SiteOwnedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        CANCELED = "canceled", "Canceled"
        ARCHIVED = "archived", "Archived"

    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public"
        UNLISTED = "unlisted", "Unlisted"
        INVITE_ONLY = "invite_only", "Invite only"

    class Recurrence(models.TextChoices):
        NONE = "none", "Does not repeat"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180)
    description = models.TextField(blank=True)
    host_name = models.CharField(max_length=160, blank=True)
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    recurrence = models.CharField(
        max_length=20, choices=Recurrence.choices, default=Recurrence.NONE
    )
    recurrence_interval = models.PositiveSmallIntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(52)]
    )
    recurrence_until = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_created",
    )

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=("site", "slug"), name="events_unique_slug_per_site"
            ),
            models.CheckConstraint(
                condition=Q(recurrence_interval__gte=1),
                name="events_recurrence_interval_positive",
            ),
        ]

    def __str__(self):
        return self.title


class EventOccurrence(SiteOwnedModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELED = "canceled", "Canceled"
        ARCHIVED = "archived", "Archived"

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="occurrences"
    )
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, validators=[validate_timezone])
    venue_name = models.CharField(max_length=180, blank=True)
    venue_address = models.CharField(max_length=300, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SCHEDULED
    )

    class Meta:
        ordering = ("starts_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="events_occurrence_ends_after_start",
            ),
            models.UniqueConstraint(
                fields=("event", "starts_at"), name="events_unique_series_start"
            ),
        ]

    def clean(self):
        super().clean()
        if self.event_id and self.site_id != self.event.site_id:
            raise ValidationError("An occurrence must belong to its event's site.")

    def __str__(self):
        return f"{self.event} at {self.starts_at}"
