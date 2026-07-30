from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "site", "kind", "read_at", "created_at")
    list_filter = ("kind", "read_at", "created_at")
    search_fields = ("title", "message", "recipient__email", "site__display_name")
