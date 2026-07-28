from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from sites.models import SiteOwnedModel


class ConsentStatus(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    GRANTED = "granted", "Granted"
    WITHDRAWN = "withdrawn", "Withdrawn"
    SUPPRESSED = "suppressed", "Suppressed"


class Contact(SiteOwnedModel):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    normalized_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    email_consent_status = models.CharField(
        max_length=20, choices=ConsentStatus.choices, default=ConsentStatus.UNKNOWN
    )
    sms_consent_status = models.CharField(
        max_length=20, choices=ConsentStatus.choices, default=ConsentStatus.UNKNOWN
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField("ContactTag", through="ContactTagAssignment")

    class Meta:
        ordering = ("last_name", "first_name", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("site", "normalized_email"),
                condition=~Q(normalized_email=""),
                name="contacts_unique_email_per_site",
            )
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.strip()
        self.normalized_email = self.email.casefold() if self.email else ""
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def archive(self):
        self.archived_at = timezone.now()
        self.save(update_fields=("archived_at", "updated_at"))

    def __str__(self):
        return self.display_name


class ContactTag(SiteOwnedModel):
    name = models.CharField(max_length=50)
    slug = models.SlugField(max_length=60)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("site", "slug"), name="contacts_unique_tag_slug_per_site"
            )
        ]

    def __str__(self):
        return self.name


class ContactTagAssignment(models.Model):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    tag = models.ForeignKey(ContactTag, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("contact", "tag"), name="contacts_one_tag_assignment"
            )
        ]

    def clean(self):
        super().clean()
        if self.contact_id and self.tag_id and self.contact.site_id != self.tag.site_id:
            raise ValidationError("A contact and tag must belong to the same site.")


class ConsentRecord(SiteOwnedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="consent_history"
    )
    channel = models.CharField(max_length=10, choices=Channel.choices)
    status = models.CharField(max_length=20, choices=ConsentStatus.choices)
    source = models.CharField(max_length=80)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-recorded_at", "-created_at")

    def clean(self):
        super().clean()
        if self.contact_id and self.site_id != self.contact.site_id:
            raise ValidationError("Consent history must belong to the contact's site.")

    def __str__(self):
        return f"{self.contact} - {self.get_channel_display()}: {self.get_status_display()}"


class Member(SiteOwnedModel):
    class AdministrativeStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    contact = models.OneToOneField(
        Contact, on_delete=models.CASCADE, related_name="membership"
    )
    administrative_status = models.CharField(
        max_length=20,
        choices=AdministrativeStatus.choices,
        default=AdministrativeStatus.ACTIVE,
    )
    starts_on = models.DateField(default=timezone.localdate)
    ends_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("contact__last_name", "contact__first_name")

    def clean(self):
        super().clean()
        if self.contact_id and self.site_id != self.contact.site_id:
            raise ValidationError("A member must belong to the contact's site.")
        if self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError("Membership cannot end before it starts.")

    @property
    def effective_status(self):
        if self.administrative_status == self.AdministrativeStatus.INACTIVE:
            return "inactive"
        subscription = self.subscriptions.order_by("-created_at").first()
        return subscription.status if subscription else "active"

    def __str__(self):
        return str(self.contact)


class MembershipPlan(SiteOwnedModel):
    class Interval(models.TextChoices):
        MONTHLY = "month", "Monthly"
        YEARLY = "year", "Yearly"

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    amount_cents = models.PositiveIntegerField(validators=[MinValueValidator(50)])
    currency = models.CharField(max_length=3)
    interval = models.CharField(max_length=10, choices=Interval.choices)
    stripe_product_id = models.CharField(max_length=255, blank=True)
    stripe_price_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name", "interval")
        constraints = [
            models.UniqueConstraint(
                fields=("site", "name", "interval"),
                name="contacts_unique_membership_plan",
            )
        ]

    def save(self, *args, **kwargs):
        self.currency = self.currency.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_interval_display()})"


class MemberSubscription(SiteOwnedModel):
    class Status(models.TextChoices):
        INCOMPLETE = "incomplete", "Incomplete"
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        MembershipPlan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.INCOMPLETE
    )
    connected_account_id = models.CharField(max_length=255)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    stripe_subscription_id = models.CharField(
        max_length=255, null=True, blank=True, unique=True
    )
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True)
    current_period_starts_at = models.DateTimeField(null=True, blank=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.member_id and self.site_id != self.member.site_id:
            raise ValidationError("A subscription must belong to the member's site.")
        if self.plan_id and self.site_id != self.plan.site_id:
            raise ValidationError("A subscription must belong to the plan's site.")

    def __str__(self):
        return f"{self.member} - {self.plan}: {self.get_status_display()}"
