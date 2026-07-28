from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ops.services import record_audit_event
from subscriptions.models import PlatformSubscription

from .models import Site, SiteDomain, SiteRole, SiteTheme


@transaction.atomic
def create_subscriber_site(
    *,
    owner,
    display_name,
    slug,
    timezone_name,
    currency=None,
    template_key="classic",
    request=None,
):
    now = timezone.now()
    site = Site.objects.create(
        display_name=display_name,
        slug=slug,
        status=Site.Status.TRIALING,
        timezone=timezone_name,
        currency=currency or settings.PLATFORM_DEFAULT_CURRENCY,
        template_key=template_key,
    )
    SiteDomain.objects.create(
        site=site,
        hostname=f"{site.slug}.{settings.PLATFORM_DOMAIN}",
        kind=SiteDomain.Kind.PLATFORM,
        is_canonical=True,
        is_verified=True,
    )
    SiteTheme.objects.create(site=site)
    SiteRole.objects.create(
        site=site,
        user=owner,
        role=SiteRole.Role.SUBSCRIBER_ADMIN,
        is_active=True,
    )
    PlatformSubscription.objects.create(
        site=site,
        status=PlatformSubscription.Status.TRIALING,
        trial_started_at=now,
        trial_ends_at=now + timedelta(days=settings.SUBSCRIPTION_TRIAL_DAYS),
        stripe_price_id="",
    )
    record_audit_event(
        action="site.created",
        actor=owner,
        site_id=site.id,
        target=site,
        summary={"status": site.status, "slug": site.slug},
        request=request,
    )
    return site


def user_site_roles(user):
    if not getattr(user, "is_authenticated", False):
        return SiteRole.objects.none()
    return SiteRole.objects.filter(user=user, is_active=True).select_related("site")
