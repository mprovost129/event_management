from django.contrib import admin

from .models import Review, ReviewModeration, ReviewReport


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "site",
        "occurrence",
        "rating",
        "moderation_status",
        "submitted_at",
    )
    list_filter = ("rating", "moderation_status")
    search_fields = ("display_name", "comment", "occurrence__event__title")
    readonly_fields = ("submitted_at", "edited_at", "deleted_at")


admin.site.register(ReviewReport)
admin.site.register(ReviewModeration)
