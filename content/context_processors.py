from django.db.models import Q
from django.utils import timezone

from .models import PublishingStatus, SitePage


def site_navigation(request):
    site = getattr(request, "site", None)
    if site is None or not site.is_published:
        return {"site_navigation": {}}
    pages = (
        SitePage.objects.for_site(site)
        .filter(
            Q(status=PublishingStatus.PUBLISHED)
            | Q(status=PublishingStatus.SCHEDULED, publish_at__lte=timezone.now())
        )
        .only("page_type", "navigation_label")
    )
    return {"site_navigation": {page.page_type: page for page in pages}}
