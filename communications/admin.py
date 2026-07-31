from django.contrib import admin

from .models import (
    Campaign,
    CampaignRecipient,
    OutboundMessage,
    ProviderCallbackEvent,
    SmsAllowance,
    SmsUsageEvent,
    UnsubscribeCapability,
)


@admin.register(OutboundMessage)
class OutboundMessageAdmin(admin.ModelAdmin):
    list_display = (
        "kind",
        "recipient_email",
        "site",
        "status",
        "attempts",
        "created_at",
        "sent_at",
    )
    list_filter = ("kind", "status")
    search_fields = ("recipient_email", "subject", "site__display_name")
    readonly_fields = ("body", "html_body", "last_error", "attempts", "sent_at")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "channel", "status", "scheduled_for", "created_at")
    list_filter = ("channel", "status", "audience")
    search_fields = ("name", "subject", "site__display_name")


@admin.register(CampaignRecipient)
class CampaignRecipientAdmin(admin.ModelAdmin):
    list_display = ("campaign", "contact", "status", "segment_count", "sent_at")
    list_filter = ("status",)
    search_fields = ("contact__email", "contact__phone", "campaign__name")


@admin.register(SmsAllowance)
class SmsAllowanceAdmin(admin.ModelAdmin):
    list_display = (
        "site",
        "period_start",
        "included_segments",
        "purchased_segments",
        "reserved_segments",
        "sent_segments",
    )


@admin.register(SmsUsageEvent)
class SmsUsageEventAdmin(admin.ModelAdmin):
    list_display = ("site", "campaign", "action", "segments", "created_at")
    list_filter = ("action",)


@admin.register(ProviderCallbackEvent)
class ProviderCallbackEventAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "event_type",
        "provider_message_id",
        "status",
        "received_at",
    )
    list_filter = ("provider", "event_type", "status")


@admin.register(UnsubscribeCapability)
class UnsubscribeCapabilityAdmin(admin.ModelAdmin):
    list_display = ("contact", "site", "channel", "campaign", "used_at")
    readonly_fields = ("token_hash",)
