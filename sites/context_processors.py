from django.urls import reverse

from core.context_processors import control_origin

from .models import SiteRole


def site_management(request):
    site = getattr(request, "site", None)
    user = getattr(request, "user", None)
    if site is None:
        return {
            "public_site_management_role": None,
            "public_site_workspace_url": None,
        }

    workspace_url = (
        f"{control_origin(request)}"
        f"{reverse('content:manage', kwargs={'site_id': site.id})}"
    )

    if user is None or not user.is_authenticated:
        return {
            "public_site_management_role": None,
            "public_site_workspace_url": workspace_url,
        }

    role = (
        SiteRole.objects.filter(site=site, user=user, is_active=True)
        .only("role", "site_id")
        .first()
    )
    return {
        "public_site_management_role": role,
        "public_site_workspace_url": workspace_url,
    }
