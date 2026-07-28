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
    max_guests = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(20)]
    )
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


class Invitation(SiteOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RESPONDED = "responded", "Responded"
        REVOKED = "revoked", "Revoked"

    occurrence = models.ForeignKey(
        EventOccurrence, on_delete=models.CASCADE, related_name="invitations"
    )
    contact = models.ForeignKey(
        "contacts.Contact", on_delete=models.CASCADE, related_name="event_invitations"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_invitations_created",
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("occurrence", "contact"),
                name="events_one_invitation_per_contact_occurrence",
            )
        ]

    def clean(self):
        super().clean()
        if self.occurrence_id and self.site_id != self.occurrence.site_id:
            raise ValidationError("An invitation must belong to its occurrence's site.")
        if self.contact_id and self.site_id != self.contact.site_id:
            raise ValidationError("An invitation must belong to its contact's site.")

    def __str__(self):
        return f"{self.contact} invited to {self.occurrence}"


class Registration(SiteOwnedModel):
    class Response(models.TextChoices):
        GOING = "going", "Going"
        MAYBE = "maybe", "Maybe"
        NOT_GOING = "not_going", "Not going"

    class Source(models.TextChoices):
        PUBLIC = "public", "Public registration"
        INVITATION = "invitation", "Invitation"
        MANAGER = "manager", "Manager override"

    occurrence = models.ForeignKey(
        EventOccurrence, on_delete=models.CASCADE, related_name="registrations"
    )
    contact = models.ForeignKey(
        "contacts.Contact", on_delete=models.CASCADE, related_name="event_registrations"
    )
    invitation = models.OneToOneField(
        Invitation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registration",
    )
    response = models.CharField(max_length=20, choices=Response.choices)
    source = models.CharField(max_length=20, choices=Source.choices)
    responded_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-responded_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("occurrence", "contact"),
                name="events_one_registration_per_contact_occurrence",
            )
        ]

    def clean(self):
        super().clean()
        if self.occurrence_id and self.site_id != self.occurrence.site_id:
            raise ValidationError(
                "A registration must belong to its occurrence's site."
            )
        if self.contact_id and self.site_id != self.contact.site_id:
            raise ValidationError("A registration must belong to its contact's site.")

    def __str__(self):
        return f"{self.contact}: {self.get_response_display()} for {self.occurrence}"


class Participant(SiteOwnedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"

    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="participants"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_primary = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        ordering = ("-is_primary", "last_name", "first_name")
        constraints = [
            models.UniqueConstraint(
                fields=("registration",),
                condition=Q(is_primary=True, status="active"),
                name="events_one_active_primary_participant",
            )
        ]

    def clean(self):
        super().clean()
        if self.registration_id and self.site_id != self.registration.site_id:
            raise ValidationError(
                "A participant must belong to its registration's site."
            )

    @property
    def display_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.display_name


class RegistrationHistory(SiteOwnedModel):
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="history"
    )
    previous_response = models.CharField(
        max_length=20, choices=Registration.Response.choices, blank=True
    )
    new_response = models.CharField(
        max_length=20, choices=Registration.Response.choices
    )
    guest_count = models.PositiveSmallIntegerField(default=0)
    participant_names = models.JSONField(default=list)
    source = models.CharField(max_length=20, choices=Registration.Source.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registration_changes",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.registration} changed to {self.get_new_response_display()}"
