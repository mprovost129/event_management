import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from .validators import validate_currency, validate_site_slug, validate_timezone

hex_color_validator = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Enter a six-digit hexadecimal color such as #336699.",
)


class Site(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        TRIALING = "trialing", "Trialing"
        ACTIVE = "active", "Active"
        GRACE = "grace", "Payment grace period"
        SUSPENDED = "suspended", "Suspended"
        CANCELED = "canceled", "Canceled"
        ARCHIVED = "archived", "Archived"

    class Template(models.TextChoices):
        CLASSIC = "classic", "Classic"
        SOCIAL = "social", "Social"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_name = models.CharField(max_length=160)
    slug = models.SlugField(
        max_length=63,
        unique=True,
        validators=[validate_site_slug],
        help_text="Used in the site's platform subdomain.",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    timezone = models.CharField(
        max_length=64, default="America/New_York", validators=[validate_timezone]
    )
    currency = models.CharField(
        max_length=3, default="usd", validators=[validate_currency]
    )
    template_key = models.CharField(
        max_length=50, choices=Template.choices, default=Template.CLASSIC
    )
    is_published = models.BooleanField(default=False)
    # CAN-SPAM requires the sender's own valid physical postal address in every
    # commercial email. The sender is the subscriber, not the platform, so this
    # cannot come from a platform-level setting.
    postal_address = models.CharField(
        max_length=300,
        blank=True,
        help_text=(
            "A valid physical mailing address, required by law at the bottom of "
            "every newsletter you send. A PO box registered to your group works."
        ),
    )
    default_refund_policy = models.TextField(
        blank=True,
        help_text=(
            "Shown to buyers before they pay and on public event pages. "
            "Individual ticket types can override it."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_name",)

    def save(self, *args, **kwargs):
        self.slug = self.slug.lower()
        self.currency = self.currency.lower()
        super().save(*args, **kwargs)

    @property
    def accepts_public_traffic(self):
        return self.status in {
            self.Status.TRIALING,
            self.Status.ACTIVE,
            self.Status.GRACE,
        }

    def __str__(self):
        return self.display_name


class SiteDomain(models.Model):
    class Kind(models.TextChoices):
        PLATFORM = "platform", "Platform subdomain"
        CUSTOM = "custom", "Custom domain"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="domains")
    hostname = models.CharField(max_length=253, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PLATFORM)
    is_canonical = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("site",),
                condition=Q(is_canonical=True),
                name="sites_one_canonical_domain",
            )
        ]

    def save(self, *args, **kwargs):
        self.hostname = self.hostname.strip().lower().rstrip(".")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.hostname


class SiteTheme(models.Model):
    site = models.OneToOneField(Site, on_delete=models.CASCADE, related_name="theme")
    logo = models.ImageField(upload_to="site-logos/%Y/%m/", blank=True)
    hero_image = models.ImageField(upload_to="site-heroes/%Y/%m/", blank=True)
    hero_heading = models.CharField(max_length=180, blank=True)
    hero_text = models.CharField(max_length=320, blank=True)
    primary_color = models.CharField(
        max_length=7, default="#0B1D39", validators=[hex_color_validator]
    )
    secondary_color = models.CharField(
        max_length=7, default="#516543", validators=[hex_color_validator]
    )
    typography_key = models.CharField(max_length=30, default="system")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Theme for {self.site}"


class SiteRole(models.Model):
    class Role(models.TextChoices):
        SUBSCRIBER_ADMIN = "subscriber_admin", "Subscriber admin"
        SITE_MANAGER = "site_manager", "Site manager"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="roles")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="site_roles"
    )
    role = models.CharField(max_length=30, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="site_roles_invited",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("site", "user"), name="sites_one_role_per_user"
            ),
            models.UniqueConstraint(
                fields=("site",),
                condition=Q(role="subscriber_admin", is_active=True),
                name="sites_one_active_subscriber_admin",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} at {self.site}"


class SiteOwnedQuerySet(models.QuerySet):
    def for_site(self, site):
        if site is None:
            return self.none()
        return self.filter(site=site)


class SiteOwnedModel(models.Model):
    """Abstract base for direct site-owned records introduced in later phases."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(Site, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SiteOwnedQuerySet.as_manager()

    class Meta:
        abstract = True
