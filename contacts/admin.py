from django.contrib import admin

from .models import ConsentRecord, Contact, ContactTag


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
