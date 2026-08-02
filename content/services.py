from django.db.models import Q
from django.utils import timezone

from ops.services import record_audit_event

from .models import BlogPost, PageSection, PublishingStatus, SitePage

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


def sync_legacy_body_section(page):
    """Mirror SitePage.body into a legacy content section for rendering."""
    section = (
        page.sections.filter(is_legacy_body=True)
        .order_by("position", "created_at")
        .first()
    )
    body = page.body.strip()
    if not body:
        if section:
            section.is_enabled = False
            section.rich_text = ""
            section.save(update_fields=("is_enabled", "rich_text", "updated_at"))
        return None

    if section is None:
        section = PageSection.objects.create(
            site=page.site,
            page=page,
            section_type=PageSection.SectionType.CONTENT,
            position=1,
            is_enabled=True,
            is_legacy_body=True,
            heading=page.title,
            rich_text=body,
        )
        return section

    section.section_type = PageSection.SectionType.CONTENT
    section.position = 1
    section.is_enabled = True
    section.heading = section.heading or page.title
    section.rich_text = body
    section.save(
        update_fields=(
            "section_type",
            "position",
            "is_enabled",
            "heading",
            "rich_text",
            "updated_at",
        )
    )
    return section


def page_has_content(page):
    if page.body.strip():
        return True
    return page.sections.filter(is_enabled=True).exists()


def resequence_sections(page):
    sections = list(page.sections.order_by("position", "created_at"))
    changed = []
    for index, section in enumerate(sections, start=1):
        if section.position != index:
            section.position = index
            changed.append(section)
    if changed:
        PageSection.objects.bulk_update(changed, ["position"])


def resequence_section_images(section):
    images = list(section.images.order_by("position", "created_at"))
    changed = []
    for index, image in enumerate(images, start=1):
        if image.position != index:
            image.position = index
            changed.append(image)
    if changed:
        section.images.model.objects.bulk_update(changed, ["position"])


def record_public_engagement(*, action, site, request=None, summary=None, target=None):
    return record_audit_event(
        action=action,
        site_id=site.id,
        target=target,
        summary=summary or {},
        request=request,
    )
