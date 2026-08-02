from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.safestring import mark_safe

from sites.models import SiteOwnedModel

from .sanitization import sanitize_rich_text


class PublishingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    SCHEDULED = "scheduled", "Scheduled"
    ARCHIVED = "archived", "Archived"


class SitePage(SiteOwnedModel):
    class PageType(models.TextChoices):
        HOME = "home", "Home"
        ABOUT = "about", "About"
        CONTACT = "contact", "Contact"
        NEWSLETTER = "newsletter", "Newsletter"

    page_type = models.CharField(max_length=20, choices=PageType.choices)
    title = models.CharField(max_length=160)
    navigation_label = models.CharField(max_length=40)
    body = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=PublishingStatus.choices, default=PublishingStatus.DRAFT
    )
    publish_at = models.DateTimeField(null=True, blank=True)
    meta_title = models.CharField(max_length=160, blank=True)
    meta_description = models.CharField(max_length=320, blank=True)

    class Meta:
        ordering = ("page_type",)
        constraints = [
            models.UniqueConstraint(
                fields=("site", "page_type"), name="content_one_page_type_per_site"
            )
        ]

    @property
    def is_public(self):
        if self.status == PublishingStatus.PUBLISHED:
            return self.publish_at is None or self.publish_at <= timezone.now()
        return (
            self.status == PublishingStatus.SCHEDULED
            and self.publish_at is not None
            and self.publish_at <= timezone.now()
        )

    def __str__(self):
        return f"{self.site}: {self.title}"

    def renderable_sections(self):
        """Return enabled sections, preferring custom sections over legacy body.

        While the editor still writes to SitePage.body, a migration-backed
        legacy section keeps public rendering on the new section pipeline.
        As soon as custom sections exist, the legacy section is omitted.
        """
        enabled = self.sections.filter(is_enabled=True).prefetch_related("images")
        custom = enabled.filter(is_legacy_body=False)
        return custom if custom.exists() else enabled


class PageSection(SiteOwnedModel):
    class SectionType(models.TextChoices):
        HERO = "hero", "Hero"
        CONTENT = "content", "Content"
        STRIP = "strip", "Logo or photo strip"

    class ImageAlignment(models.TextChoices):
        LEFT = "left", "Image left"
        RIGHT = "right", "Image right"

    page = models.ForeignKey(SitePage, on_delete=models.CASCADE, related_name="sections")
    section_type = models.CharField(max_length=20, choices=SectionType.choices)
    position = models.PositiveIntegerField(default=1)
    is_enabled = models.BooleanField(default=True)
    is_legacy_body = models.BooleanField(default=False)

    heading = models.CharField(max_length=180, blank=True)
    subheading = models.CharField(max_length=320, blank=True)
    rich_text = models.TextField(blank=True)
    image = models.ImageField(upload_to="page-sections/%Y/%m/", blank=True)
    image_alignment = models.CharField(
        max_length=10,
        choices=ImageAlignment.choices,
        default=ImageAlignment.RIGHT,
    )
    button_text = models.CharField(max_length=40, blank=True)
    button_url = models.URLField(max_length=500, blank=True)

    class Meta:
        ordering = ("position", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(position__gte=1),
                name="content_page_section_position_positive",
            )
        ]

    def clean(self):
        super().clean()
        if self.page_id and self.site_id != self.page.site_id:
            raise ValidationError(
                "A section must belong to the same site as its page."
            )

    def __str__(self):
        return f"{self.page} [{self.get_section_type_display()} #{self.position}]"

    @property
    def rich_text_html(self):
        return mark_safe(sanitize_rich_text(self.rich_text))


class PageSectionImage(SiteOwnedModel):
    section = models.ForeignKey(
        PageSection,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="page-sections/%Y/%m/")
    alt_text = models.CharField(max_length=180)
    position = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("position", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(position__gte=1),
                name="content_page_section_image_position_positive",
            )
        ]

    def clean(self):
        super().clean()
        if self.section_id and self.site_id != self.section.site_id:
            raise ValidationError(
                "A section image must belong to the same site as its section."
            )

    def __str__(self):
        return f"{self.section} image #{self.position}"


class BlogPost(SiteOwnedModel):
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180)
    excerpt = models.CharField(max_length=400, blank=True)
    body = models.TextField()
    featured_image = models.ImageField(upload_to="blog/%Y/%m/", blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blog_posts",
    )
    author_display_name = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20, choices=PublishingStatus.choices, default=PublishingStatus.DRAFT
    )
    publish_at = models.DateTimeField(null=True, blank=True, db_index=True)
    meta_description = models.CharField(max_length=320, blank=True)

    class Meta:
        ordering = ("-publish_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("site", "slug"), name="content_unique_blog_slug_per_site"
            ),
            models.CheckConstraint(
                condition=~Q(status=PublishingStatus.SCHEDULED)
                | Q(publish_at__isnull=False),
                name="content_scheduled_post_has_publish_at",
            ),
        ]

    @property
    def is_public(self):
        if self.status == PublishingStatus.PUBLISHED:
            return self.publish_at is None or self.publish_at <= timezone.now()
        return (
            self.status == PublishingStatus.SCHEDULED
            and self.publish_at is not None
            and self.publish_at <= timezone.now()
        )

    def __str__(self):
        return self.title
