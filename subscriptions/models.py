import uuid

from django.db import models
from django.db.models import F, Q


class PlatformSubscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        GRACE = "grace", "Payment grace period"
        SUSPENDED = "suspended", "Suspended"
        CANCELED = "canceled", "Canceled"
        ARCHIVED = "archived", "Archived"

    class BillingInterval(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.OneToOneField(
        "sites.Site", on_delete=models.CASCADE, related_name="platform_subscription"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TRIALING, db_index=True
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(
        max_length=255, blank=True, unique=True, null=True
    )
    stripe_price_id = models.CharField(max_length=255, blank=True)
    billing_interval = models.CharField(
        max_length=10, choices=BillingInterval.choices, blank=True
    )
    trial_started_at = models.DateTimeField()
    trial_ends_at = models.DateTimeField()
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(trial_ends_at__gt=F("trial_started_at")),
                name="subscriptions_trial_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.site} - {self.get_status_display()}"


class StripeWebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-received_at",)

    def __str__(self):
        return f"{self.event_type} ({self.stripe_event_id})"
