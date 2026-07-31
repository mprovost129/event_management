from django.conf import settings

from sites.models import SiteRole


def _request_scheme(request):
    return "https" if request.is_secure() else "http"


def _control_host():
    control_hosts = list(getattr(settings, "PLATFORM_CONTROL_HOSTS", ()) or ())
    return control_hosts[0] if control_hosts else settings.PLATFORM_DOMAIN


def _site_public_url(request, role):
    canonical = role.site.domains.filter(is_canonical=True, is_verified=True).first()
    if canonical is None:
        return None
    return f"{_request_scheme(request)}://{canonical.hostname}"


def account_navigation(request):
    user = getattr(request, "user", None)
    help_url = f"{_request_scheme(request)}://{_control_host()}/help/"
    if user is None or not user.is_authenticated:
        return {
            "nav_primary_site_url": None,
            "nav_primary_site_name": "",
            "nav_avatar_initials": "GH",
            "nav_avatar_url": "",
            "nav_has_any_site": False,
            "platform_help_url": help_url,
        }

    roles = SiteRole.objects.filter(user=user, is_active=True).select_related("site")
    primary_role = roles.order_by("site__display_name").first()
    published_role = (
        roles.filter(
            site__is_published=True,
            site__status__in=("trialing", "active", "grace"),
        )
        .order_by("site__display_name")
        .first()
    )

    nav_site_url = _site_public_url(request, published_role) if published_role else None
    nav_site_name = published_role.site.display_name if published_role else ""

    first = (user.first_name or "").strip()[:1]
    last = (user.last_name or "").strip()[:1]
    fallback = (user.username or user.email or "GH").strip()[:2].upper()
    initials = f"{first}{last}".upper() if first or last else fallback

    return {
        "nav_primary_site_url": nav_site_url,
        "nav_primary_site_name": nav_site_name,
        "nav_avatar_initials": initials,
        "nav_avatar_url": user.avatar.url if getattr(user, "avatar", None) else "",
        "nav_has_any_site": primary_role is not None,
        "platform_help_url": help_url,
    }
