from django.contrib import admin

from .models import Site, SiteDomain, SiteRole, SiteTheme


class SiteDomainInline(admin.TabularInline):
    model = SiteDomain
    extra = 0


class SiteRoleInline(admin.TabularInline):
    model = SiteRole
    fk_name = "site"
    extra = 0


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("display_name", "slug", "status", "is_published", "created_at")
    list_filter = ("status", "is_published", "template_key")
    search_fields = ("display_name", "slug")
    inlines = (SiteDomainInline, SiteRoleInline)


@admin.register(SiteTheme)
class SiteThemeAdmin(admin.ModelAdmin):
    list_display = ("site", "primary_color", "secondary_color", "typography_key")
