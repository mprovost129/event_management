from django.contrib import admin

from .models import BlogPost, PageSection, PageSectionImage, SitePage


class PageSectionImageInline(admin.TabularInline):
    model = PageSectionImage
    extra = 0


@admin.register(SitePage)
class SitePageAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "page_type", "status", "publish_at")
    list_filter = ("page_type", "status")
    search_fields = ("title", "site__display_name")


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "site", "status", "publish_at")
    list_filter = ("status",)
    search_fields = ("title", "site__display_name")


@admin.register(PageSection)
class PageSectionAdmin(admin.ModelAdmin):
    list_display = (
        "page",
        "section_type",
        "position",
        "is_enabled",
        "is_legacy_body",
    )
    list_filter = ("section_type", "is_enabled", "is_legacy_body")
    search_fields = ("page__title", "site__display_name", "heading")
    inlines = [PageSectionImageInline]


@admin.register(PageSectionImage)
class PageSectionImageAdmin(admin.ModelAdmin):
    list_display = ("section", "position", "alt_text")
    list_filter = ("section__section_type",)
    search_fields = ("section__page__title", "alt_text", "site__display_name")
