from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from sites.models import SiteOwnedModel


class ConnectedAccount(SiteOwnedModel):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        PENDING = "pending", "Onboarding incomplete"
        READY = "ready", "Ready for payments"
        RESTRICTED = "restricted", "Needs attention"
        DISCONNECTED = "disconnected", "Disconnected"

    site = models.OneToOneField(
        "sites.Site", on_delete=models.CASCADE, related_name="connected_account"
    )
    stripe_account_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    country = models.CharField(max_length=2, blank=True)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    details_submitted = models.BooleanField(default=False)
    requirements_due = models.JSONField(default=list, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    disconnected_at = models.DateTimeField(null=True, blank=True)
    sync_failure_count = models.PositiveSmallIntegerField(default=0)
    permanent_sync_failure_count = models.PositiveSmallIntegerField(default=0)
    last_sync_attempted_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.CharField(max_length=500, blank=True)

    @property
    def commerce_ready(self):
        return (
            self.status == self.Status.READY
            and self.charges_enabled
            and self.payouts_enabled
            and not self.disconnected_at
        )

    def __str__(self):
        return f"{self.site} - {self.get_status_display()}"


class TicketType(SiteOwnedModel):
    occurrence = models.ForeignKey(
        "events.EventOccurrence",
        on_delete=models.CASCADE,
        related_name="ticket_types",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    amount_cents = models.PositiveIntegerField(validators=[MinValueValidator(50)])
    currency = models.CharField(max_length=3)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    max_per_order = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(1)]
    )
    sales_start_at = models.DateTimeField(null=True, blank=True)
    sales_end_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("amount_cents", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("occurrence", "name"), name="payments_unique_ticket_name"
            ),
            models.CheckConstraint(
                condition=Q(sales_end_at__isnull=True)
                | Q(sales_start_at__isnull=True)
                | Q(sales_end_at__gt=F("sales_start_at")),
                name="payments_ticket_sales_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        if self.occurrence_id and self.site_id != self.occurrence.site_id:
            raise ValidationError("A ticket type must belong to its occurrence's site.")
        if (
            self.currency
            and self.site_id
            and self.currency.lower() != self.site.currency
        ):
            raise ValidationError("Ticket currency must match the site currency.")

    def save(self, *args, **kwargs):
        self.currency = self.currency.lower()
        super().save(*args, **kwargs)

    def sales_are_open(self, now=None):
        now = now or timezone.now()
        return (
            self.is_active
            and (not self.sales_start_at or self.sales_start_at <= now)
            and (not self.sales_end_at or self.sales_end_at > now)
        )

    def __str__(self):
        return f"{self.occurrence}: {self.name}"


class Order(SiteOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending payment"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        EXPIRED = "expired", "Checkout expired"
        PARTIALLY_REFUNDED = "partially_refunded", "Partially refunded"
        REFUNDED = "refunded", "Refunded"
        DISPUTED = "disputed", "Disputed"

    occurrence = models.ForeignKey(
        "events.EventOccurrence", on_delete=models.PROTECT, related_name="orders"
    )
    registration = models.ForeignKey(
        "events.Registration", on_delete=models.PROTECT, related_name="orders"
    )
    purchaser = models.ForeignKey(
        "contacts.Contact", on_delete=models.PROTECT, related_name="orders"
    )
    connected_account_id = models.CharField(max_length=255)
    currency = models.CharField(max_length=3)
    subtotal_cents = models.PositiveIntegerField()
    total_cents = models.PositiveIntegerField()
    refunded_cents = models.PositiveIntegerField(default=0)
    application_fee_bps = models.PositiveSmallIntegerField(default=0)
    application_fee_cents = models.PositiveIntegerField(default=0)
    application_fee_refunded_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True)
    stripe_charge_id = models.CharField(max_length=255, blank=True)
    stripe_balance_transaction_id = models.CharField(max_length=255, blank=True)
    stripe_fee_cents = models.PositiveIntegerField(null=True, blank=True)
    stripe_net_cents = models.IntegerField(null=True, blank=True)
    checkout_expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(application_fee_bps__lte=9999),
                name="payments_order_application_fee_bps_valid",
            ),
            models.CheckConstraint(
                condition=Q(application_fee_cents__lte=F("total_cents")),
                name="payments_order_application_fee_not_over_total",
            ),
            models.CheckConstraint(
                condition=Q(
                    application_fee_refunded_cents__lte=F("application_fee_cents")
                ),
                name="payments_order_fee_refund_not_over_fee",
            ),
        ]

    def clean(self):
        super().clean()
        related = (self.occurrence, self.registration, self.purchaser)
        if self.site_id and any(item.site_id != self.site_id for item in related):
            raise ValidationError("Order records must all belong to the same site.")
        if (
            self.currency
            and self.site_id
            and self.currency.lower() != self.site.currency
        ):
            raise ValidationError("Order currency must match the site currency.")
        if self.refunded_cents > self.total_cents:
            raise ValidationError("Refunded amount cannot exceed the order total.")
        if self.application_fee_cents > self.total_cents:
            raise ValidationError("Application fee cannot exceed the order total.")
        if self.application_fee_refunded_cents > self.application_fee_cents:
            raise ValidationError(
                "Refunded application fee cannot exceed the collected fee."
            )

    def __str__(self):
        return f"Order {str(self.id)[:8]} - {self.get_status_display()}"


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    ticket_type = models.ForeignKey(
        TicketType, null=True, on_delete=models.SET_NULL, related_name="order_lines"
    )
    description = models.CharField(max_length=180)
    unit_amount_cents = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField()
    line_total_cents = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.pk and OrderLine.objects.filter(pk=self.pk).exists():
            raise ValidationError("Order line snapshots cannot be changed.")
        self.line_total_cents = self.unit_amount_cents * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} x {self.quantity}"


class InventoryHold(SiteOwnedModel):
    class Status(models.TextChoices):
        HELD = "held", "Held"
        CONVERTED = "converted", "Converted"
        RELEASED = "released", "Released"

    ticket_type = models.ForeignKey(
        TicketType, on_delete=models.CASCADE, related_name="inventory_holds"
    )
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="inventory_hold"
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.HELD
    )
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ("expires_at",)

    def clean(self):
        super().clean()
        if self.ticket_type_id and self.site_id != self.ticket_type.site_id:
            raise ValidationError("A hold must belong to its ticket type's site.")
        if self.order_id and self.site_id != self.order.site_id:
            raise ValidationError("A hold must belong to its order's site.")


class Ticket(SiteOwnedModel):
    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        REFUNDED = "refunded", "Refunded"
        VOID = "void", "Void"

    order_line = models.ForeignKey(
        OrderLine, on_delete=models.PROTECT, related_name="tickets"
    )
    participant = models.OneToOneField(
        "events.Participant", on_delete=models.PROTECT, related_name="ticket"
    )
    display_code = models.CharField(max_length=20, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.VALID
    )

    class Meta:
        ordering = ("participant__last_name", "participant__first_name")

    def clean(self):
        super().clean()
        if self.participant_id and self.site_id != self.participant.site_id:
            raise ValidationError("A ticket must belong to its participant's site.")
        if self.order_line_id and self.site_id != self.order_line.order.site_id:
            raise ValidationError("A ticket must belong to its order's site.")


class Refund(SiteOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    amount_cents = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    stripe_refund_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commerce_refunds_created",
    )
    succeeded_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.order_id and self.site_id != self.order.site_id:
            raise ValidationError("A refund must belong to its order's site.")


class Dispute(SiteOwnedModel):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="disputes")
    stripe_dispute_id = models.CharField(max_length=255, unique=True)
    amount_cents = models.PositiveIntegerField()
    status = models.CharField(max_length=40)
    reason = models.CharField(max_length=80, blank=True)
    due_by = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class FinancialTransition(SiteOwnedModel):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="financial_history"
    )
    refund = models.ForeignKey(
        Refund,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="history",
    )
    event_type = models.CharField(max_length=120)
    previous_status = models.CharField(max_length=40, blank=True)
    new_status = models.CharField(max_length=40)
    stripe_event_id = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)


class ConnectWebhookEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    stripe_event_id = models.CharField(max_length=255, unique=True)
    connected_account_id = models.CharField(max_length=255, blank=True, db_index=True)
    event_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=255, blank=True)
    livemode = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-received_at",)

    def __str__(self):
        return f"{self.event_type} ({self.stripe_event_id})"


class MembershipPayment(SiteOwnedModel):
    class Status(models.TextChoices):
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"

    member_subscription = models.ForeignKey(
        "contacts.MemberSubscription",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    stripe_invoice_id = models.CharField(max_length=255, unique=True)
    amount_due_cents = models.PositiveIntegerField(default=0)
    amount_paid_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=20, choices=Status.choices)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if (
            self.member_subscription_id
            and self.site_id != self.member_subscription.site_id
        ):
            raise ValidationError(
                "A membership payment must belong to its subscription's site."
            )
