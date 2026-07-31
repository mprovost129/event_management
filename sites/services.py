from datetime import timedelta
from typing import NamedTuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ops.services import record_audit_event
from subscriptions.models import PlatformSubscription

from .models import Site, SiteDomain, SiteRole, SiteTheme


class SiteCreationDecision(NamedTuple):
    allowed: bool
    reason: str = ""


class SiteCreationNotAllowed(Exception):
    pass


def subscriber_site_creation_decision(user):
    owned_subscriptions = PlatformSubscription.objects.filter(
        site__roles__user=user,
        site__roles__role=SiteRole.Role.SUBSCRIBER_ADMIN,
        site__roles__is_active=True,
    )
    if not owned_subscriptions.exists():
        return SiteCreationDecision(True)
    if owned_subscriptions.filter(status=PlatformSubscription.Status.TRIALING).exists():
        return SiteCreationDecision(
            False,
            "You already have an organization in its trial. Upgrade it before "
            "starting another trial.",
        )
    if not owned_subscriptions.filter(
        status=PlatformSubscription.Status.ACTIVE
    ).exists():
        return SiteCreationDecision(
            False,
            "Additional organizations require an active paid Gather HQs subscription.",
        )
    return SiteCreationDecision(True)


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
    locked_owner = owner.__class__._default_manager.select_for_update().get(pk=owner.pk)
    decision = subscriber_site_creation_decision(locked_owner)
    if not decision.allowed:
        raise SiteCreationNotAllowed(decision.reason)

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
        user=locked_owner,
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
    from content.services import initialize_site_content

    initialize_site_content(site)
    record_audit_event(
        action="site.created",
        actor=locked_owner,
        site_id=site.id,
        target=site,
        summary={"status": site.status, "slug": site.slug},
        request=request,
    )
    return site


def user_site_roles(user):
    if not getattr(user, "is_authenticated", False):
        return SiteRole.objects.none()
    return (
        SiteRole.objects.filter(user=user, is_active=True)
        .select_related("site")
        .prefetch_related("site__domains")
    )


def site_setup_progress(site):
    from contacts.models import Contact
    from events.models import Event
    from payments.models import ConnectedAccount

    connected = ConnectedAccount.objects.filter(site=site).first()
    subscription = site.platform_subscription
    checks = [
        {
            "key": "website",
            "label": "Publish your website",
            "description": "Choose your design and make the site visible to your group.",
            "complete": site.is_published,
        },
        {
            "key": "event",
            "label": "Publish your first event",
            "description": "Add the date, venue, guest allowance, and RSVP settings.",
            "complete": Event.objects.for_site(site)
            .filter(status=Event.Status.PUBLISHED)
            .exists(),
        },
        {
            "key": "contacts",
            "label": "Add your first contact",
            "description": "Start the list you will use for invitations and updates.",
            "complete": Contact.objects.for_site(site).exists(),
        },
        {
            "key": "stripe",
            "label": "Connect Stripe",
            "description": "Complete hosted onboarding for tickets and member dues.",
            "complete": bool(connected and connected.commerce_ready),
        },
        {
            "key": "subscription",
            "label": "Choose monthly or yearly billing",
            "description": "Subscribe before the 14-day trial ends to keep the site active.",
            "complete": bool(
                subscription.stripe_customer_id
                and subscription.stripe_subscription_id
                and subscription.billing_interval
            ),
        },
    ]
    completed = sum(check["complete"] for check in checks)
    return {
        "checks": checks,
        "completed": completed,
        "total": len(checks),
        "percent": round(completed * 100 / len(checks)),
        "next": next((check for check in checks if not check["complete"]), None),
    }
