from django.contrib import admin

from .models import PlatformSubscription, StripeWebhookEvent


@admin.register(PlatformSubscription)
class PlatformSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "site",
        "status",
        "billing_interval",
        "trial_ends_at",
        "current_period_ends_at",
    )
    list_filter = ("status", "billing_interval", "cancel_at_period_end")
    search_fields = (
        "site__display_name",
        "stripe_customer_id",
        "stripe_subscription_id",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "stripe_event_id", "status", "received_at")
    list_filter = ("status", "event_type")
    search_fields = ("stripe_event_id", "object_id")
    readonly_fields = (
        "id",
        "stripe_event_id",
        "event_type",
        "object_id",
        "status",
        "error",
        "received_at",
        "processed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
