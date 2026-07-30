from .models import SiteRole


def site_management(request):
    site = getattr(request, "site", None)
    user = getattr(request, "user", None)
    if site is None or user is None or not user.is_authenticated:
        return {"public_site_management_role": None}
    role = (
        SiteRole.objects.filter(site=site, user=user, is_active=True)
        .only("role", "site_id")
        .first()
    )
    return {"public_site_management_role": role}
