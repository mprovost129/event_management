from django.contrib import admin

from .models import (
    ConsentRecord,
    Contact,
    ContactTag,
    Member,
    MembershipPlan,
    MemberSubscription,
)


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "site",
        "email",
        "email_consent_status",
        "archived_at",
    )
    list_filter = ("email_consent_status", "sms_consent_status")
    search_fields = ("first_name", "last_name", "email", "site__display_name")


@admin.register(ContactTag)
class ContactTagAdmin(admin.ModelAdmin):
    list_display = ("name", "site")
    search_fields = ("name", "site__display_name")


@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("contact", "site", "channel", "status", "source", "recorded_at")
    list_filter = ("channel", "status", "source")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("contact", "site", "administrative_status", "starts_on", "ends_on")
    list_filter = ("administrative_status",)
    search_fields = ("contact__first_name", "contact__last_name", "contact__email")


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "site", "amount_cents", "currency", "interval", "is_active")
    list_filter = ("interval", "is_active", "currency")


@admin.register(MemberSubscription)
class MemberSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("member", "plan", "site", "status", "current_period_ends_at")
    list_filter = ("status",)
    readonly_fields = ("stripe_customer_id", "stripe_subscription_id")
