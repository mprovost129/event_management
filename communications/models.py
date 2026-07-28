from django.db import models
from django.db.models import Q
from django.utils import timezone

from sites.models import SiteOwnedModel


class OutboundMessage(SiteOwnedModel):
    class Kind(models.TextChoices):
        INVITATION = "invitation", "Invitation"
        CONFIRMATION = "confirmation", "RSVP confirmation"
        EVENT_UPDATE = "event_update", "Event update"
        CANCELLATION = "cancellation", "Cancellation"
        REMINDER = "reminder", "Reminder"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)
    dedupe_key = models.CharField(max_length=255, blank=True)
    occurrence = models.ForeignKey(
        "events.EventOccurrence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_messages",
    )
    registration = models.ForeignKey(
        "events.Registration",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_messages",
    )
    invitation = models.ForeignKey(
        "events.Invitation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_messages",
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("site", "dedupe_key"),
                condition=~Q(dedupe_key=""),
                name="communications_unique_dedupe_key_per_site",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} to {self.recipient_email}"
