from django.contrib import admin

from .models import Event, EventOccurrence


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "status", "visibility", "recurrence")
    list_filter = ("status", "visibility", "recurrence")
    search_fields = ("title", "site__display_name")


@admin.register(EventOccurrence)
class EventOccurrenceAdmin(admin.ModelAdmin):
    list_display = ("event", "site", "starts_at", "status", "venue_name")
    list_filter = ("status", "timezone")
