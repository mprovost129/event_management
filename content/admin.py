from django.contrib import admin

from .models import BlogPost, SitePage


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
