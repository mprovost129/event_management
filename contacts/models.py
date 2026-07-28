from django.core.exceptions import ValidationError
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
