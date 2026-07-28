from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "site_id",
        "actor",
        "target_type",
        "target_id",
    )
    list_filter = ("action", "target_type")
    search_fields = ("request_id", "target_id", "actor__email")
    readonly_fields = (
        "id",
        "site_id",
        "actor",
        "request_id",
        "action",
        "target_type",
        "target_id",
        "summary",
        "ip_address",
        "user_agent",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
