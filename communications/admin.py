from django.contrib import admin

from .models import OutboundMessage


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
    readonly_fields = ("body", "last_error", "attempts", "sent_at")
