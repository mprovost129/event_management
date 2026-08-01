from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from sites.models import SiteOwnedModel


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
