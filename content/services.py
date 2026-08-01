from django.db.models import Q
from django.utils import timezone

from .models import BlogPost, PublishingStatus, SitePage

DEFAULT_PAGES = {
    SitePage.PageType.HOME: ("Home", "Home"),
    SitePage.PageType.ABOUT: ("About", "About"),
    SitePage.PageType.CONTACT: ("Contact", "Contact"),
    SitePage.PageType.NEWSLETTER: ("Newsletter", "Newsletter"),
}


def initialize_site_content(site):
    pages = []
    for page_type, (title, navigation_label) in DEFAULT_PAGES.items():
        page, _ = SitePage.objects.get_or_create(
            site=site,
            page_type=page_type,
            defaults={"title": title, "navigation_label": navigation_label},
        )
        pages.append(page)
    return pages


def public_page(site, page_type):
    now = timezone.now()
    return (
        SitePage.objects.for_site(site)
        .filter(page_type=page_type)
        .filter(
            Q(status=PublishingStatus.PUBLISHED)
            & (Q(publish_at__isnull=True) | Q(publish_at__lte=now))
            | Q(status=PublishingStatus.SCHEDULED, publish_at__lte=now)
        )
        .first()
    )


def public_blog_posts(site):
    now = timezone.now()
    return (
        BlogPost.objects.for_site(site)
        .filter(
            Q(status=PublishingStatus.PUBLISHED)
            & (Q(publish_at__isnull=True) | Q(publish_at__lte=now))
            | Q(status=PublishingStatus.SCHEDULED, publish_at__lte=now)
        )
        .select_related("author")
        .order_by("-publish_at", "-created_at")
    )
