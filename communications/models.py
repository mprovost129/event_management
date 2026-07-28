from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from sites.models import SiteOwnedModel


class OutboundMessage(SiteOwnedModel):
    class Kind(models.TextChoices):
        INVITATION = "invitation", "Invitation"
        CONFIRMATION = "confirmation", "RSVP confirmation"
        EVENT_UPDATE = "event_update", "Event update"
        CANCELLATION = "cancellation", "Cancellation"
        REMINDER = "reminder", "Reminder"
        TICKET_RECEIPT = "ticket_receipt", "Ticket receipt"
        MEMBERSHIP_RECEIPT = "membership_receipt", "Membership receipt"
        CAMPAIGN = "campaign", "Campaign"
        CAMPAIGN_TEST = "campaign_test", "Campaign test"
        REVIEW_REQUEST = "review_request", "Review request"

    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        BOUNCED = "bounced", "Bounced"
        OPENED = "opened", "Opened"
        CLICKED = "clicked", "Clicked"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
        SUPPRESSED = "suppressed", "Suppressed"
        FAILED = "failed", "Failed"

    channel = models.CharField(
        max_length=10, choices=Channel.choices, default=Channel.EMAIL
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_messages",
    )
    campaign = models.ForeignKey(
        "Campaign",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_messages",
    )
    campaign_recipient = models.OneToOneField(
        "CampaignRecipient",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_message",
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    recipient_email = models.EmailField(blank=True)
    recipient_phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_marketing = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True
    )
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    unsubscribe_url = models.CharField(max_length=500, blank=True)
    sms_segments = models.PositiveSmallIntegerField(default=0)
    sms_allowance = models.ForeignKey(
        "SmsAllowance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbound_messages",
    )
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
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
            ),
            models.CheckConstraint(
                condition=Q(channel="email", recipient_email__gt="")
                | Q(channel="sms", recipient_phone__gt=""),
                name="communications_message_has_channel_address",
            ),
        ]

    def __str__(self):
        address = self.recipient_email or self.recipient_phone
        return f"{self.get_kind_display()} to {address}"


class Campaign(SiteOwnedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email newsletter"
        SMS = "sms", "SMS announcement"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        EXPANDING = "expanding", "Building audience"
        SENDING = "sending", "Sending"
        SENT = "sent", "Completed"
        CANCELED = "canceled", "Canceled"
        FAILED = "failed", "Failed"

    class Audience(models.TextChoices):
        ALL = "all", "All eligible contacts"
        MEMBERS = "members", "Members"
        NON_MEMBERS = "non_members", "Non-members"
        EVENT_INVITEES = "event_invitees", "Event invitees"
        RESPONSE = "response", "Event response status"
        TAG = "tag", "Contact tag"

    name = models.CharField(max_length=160)
    channel = models.CharField(
        max_length=10, choices=Channel.choices, default=Channel.EMAIL
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    audience = models.CharField(
        max_length=30, choices=Audience.choices, default=Audience.ALL
    )
    audience_tag = models.ForeignKey(
        "contacts.ContactTag",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campaigns",
    )
    audience_occurrence = models.ForeignKey(
        "events.EventOccurrence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campaigns",
    )
    response_filter = models.CharField(max_length=20, blank=True)
    source_blog_post = models.ForeignKey(
        "content.BlogPost",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seeded_campaigns",
    )
    duplicated_from = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicates",
    )
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    usage_confirmed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    eligible_count = models.PositiveIntegerField(default=0)
    excluded_count = models.PositiveIntegerField(default=0)
    estimated_segments = models.PositiveIntegerField(default=0)
    sms_reserved_segments = models.PositiveIntegerField(default=0)
    sms_allowance = models.ForeignKey(
        "SmsAllowance",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campaigns",
    )
    last_error = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="campaigns_created",
    )

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.audience == self.Audience.TAG and not self.audience_tag_id:
            raise ValidationError("Choose a contact tag for this audience.")
        if (
            self.audience
            in (
                self.Audience.EVENT_INVITEES,
                self.Audience.RESPONSE,
            )
            and not self.audience_occurrence_id
        ):
            raise ValidationError("Choose an event occurrence for this audience.")
        if self.audience == self.Audience.RESPONSE and not self.response_filter:
            raise ValidationError("Choose a response status for this audience.")
        if self.channel == self.Channel.EMAIL and not self.subject.strip():
            raise ValidationError("Email campaigns require a subject.")
        for related in (
            self.audience_tag,
            self.audience_occurrence,
            self.source_blog_post,
        ):
            if related is not None and related.site_id != self.site_id:
                raise ValidationError(
                    "Campaign selections must belong to the same site."
                )

    def __str__(self):
        return self.name


class CampaignRecipient(SiteOwnedModel):
    class Status(models.TextChoices):
        EXCLUDED = "excluded", "Excluded"
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        BOUNCED = "bounced", "Bounced"
        FAILED = "failed", "Failed"
        OPENED = "opened", "Opened"
        CLICKED = "clicked", "Clicked"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"
        SUPPRESSED = "suppressed", "Suppressed"

    campaign = models.ForeignKey(
        Campaign, on_delete=models.CASCADE, related_name="recipients"
    )
    contact = models.ForeignKey(
        "contacts.Contact", on_delete=models.PROTECT, related_name="campaign_deliveries"
    )
    address = models.CharField(max_length=320, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    exclusion_reason = models.CharField(max_length=120, blank=True)
    segment_count = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=1000, blank=True)

    class Meta:
        ordering = ("contact__last_name", "contact__first_name")
        constraints = [
            models.UniqueConstraint(
                fields=("campaign", "contact"),
                name="communications_one_recipient_per_campaign",
            )
        ]

    def clean(self):
        super().clean()
        if self.site_id and (
            self.campaign.site_id != self.site_id
            or self.contact.site_id != self.site_id
        ):
            raise ValidationError("Campaign recipients must belong to one site.")


class UnsubscribeCapability(SiteOwnedModel):
    contact = models.ForeignKey(
        "contacts.Contact", on_delete=models.CASCADE, related_name="unsubscribe_links"
    )
    campaign = models.ForeignKey(
        Campaign,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unsubscribe_links",
    )
    channel = models.CharField(max_length=10, choices=OutboundMessage.Channel.choices)
    token_hash = models.CharField(max_length=64, unique=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class SmsAllowance(SiteOwnedModel):
    period_start = models.DateField()
    included_segments = models.PositiveIntegerField(default=0)
    purchased_segments = models.PositiveIntegerField(default=0)
    reserved_segments = models.PositiveIntegerField(default=0)
    sent_segments = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-period_start",)
        constraints = [
            models.UniqueConstraint(
                fields=("site", "period_start"),
                name="communications_one_sms_allowance_period",
            ),
            models.CheckConstraint(
                condition=Q(reserved_segments__gte=0),
                name="communications_sms_reserved_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(sent_segments__gte=0),
                name="communications_sms_sent_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(
                    reserved_segments__lte=F("included_segments")
                    + F("purchased_segments")
                    - F("sent_segments")
                ),
                name="communications_sms_reserved_within_allowance",
            ),
        ]

    @property
    def remaining_segments(self):
        return max(
            0,
            self.included_segments
            + self.purchased_segments
            - self.reserved_segments
            - self.sent_segments,
        )


class SmsUsageEvent(SiteOwnedModel):
    class Action(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        ACCEPTED = "accepted", "Accepted by provider"
        RELEASED = "released", "Released"
        ADJUSTED = "adjusted", "Adjusted"

    campaign = models.ForeignKey(
        Campaign,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sms_usage",
    )
    recipient = models.ForeignKey(
        CampaignRecipient,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sms_usage",
    )
    allowance = models.ForeignKey(
        SmsAllowance, on_delete=models.PROTECT, related_name="history"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    segments = models.PositiveIntegerField()

    class Meta:
        ordering = ("-created_at",)


class ProviderCallbackEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        IGNORED = "ignored", "Ignored"
        FAILED = "failed", "Failed"

    provider = models.CharField(max_length=50)
    provider_event_id = models.CharField(max_length=255)
    provider_message_id = models.CharField(max_length=255, blank=True)
    event_type = models.CharField(max_length=50)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.RECEIVED
    )
    error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("provider", "provider_event_id"),
                name="communications_unique_provider_callback",
            )
        ]
