from django.contrib import admin

from .models import AttendanceRecord, AttendanceStatus


@admin.register(AttendanceStatus)
class AttendanceStatusAdmin(admin.ModelAdmin):
    list_display = ("participant", "site", "checked_in_at", "checked_in_by")
    list_filter = ("checked_in_at",)
    search_fields = ("participant__first_name", "participant__last_name")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("participant", "occurrence", "action", "actor", "recorded_at")
    list_filter = ("action",)
    search_fields = ("participant__first_name", "participant__last_name")
