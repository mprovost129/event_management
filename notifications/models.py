import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        RSVP = "rsvp", "Event response"
        EVENT_UPDATE = "event_update", "Event update"
        PAYMENT = "payment", "Payment update"
        TEAM = "team", "Team update"
        SYSTEM = "system", "System update"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    site = models.ForeignKey(
        "sites.Site",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=180)
    message = models.TextField()
    action_url = models.CharField(max_length=500, blank=True)
    dedupe_key = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "dedupe_key"),
                condition=~models.Q(dedupe_key=""),
                name="notifications_unique_recipient_dedupe",
            )
        ]

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return f"{self.recipient}: {self.title}"
