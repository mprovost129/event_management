from django.contrib import admin

from .models import (
    Event,
    EventOccurrence,
    Invitation,
    Participant,
    Registration,
    RegistrationHistory,
)


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "status", "visibility", "recurrence")
    list_filter = ("status", "visibility", "recurrence")
    search_fields = ("title", "site__display_name")


@admin.register(EventOccurrence)
class EventOccurrenceAdmin(admin.ModelAdmin):
    list_display = ("event", "site", "starts_at", "status", "venue_name")
    list_filter = ("status", "timezone")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("contact", "occurrence", "site", "status", "sent_at")
    list_filter = ("status",)
    search_fields = ("contact__email", "occurrence__event__title")
    readonly_fields = ("token_hash",)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("contact", "occurrence", "response", "source", "responded_at")
    list_filter = ("response", "source")
    search_fields = ("contact__email", "occurrence__event__title")


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("display_name", "registration", "is_primary", "status")
    list_filter = ("is_primary", "status")
    search_fields = ("first_name", "last_name", "email")


@admin.register(RegistrationHistory)
class RegistrationHistoryAdmin(admin.ModelAdmin):
    list_display = ("registration", "previous_response", "new_response", "created_at")
    list_filter = ("new_response", "source")
    readonly_fields = ("participant_names",)
