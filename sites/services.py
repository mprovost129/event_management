from datetime import timedelta
from typing import NamedTuple

import stripe
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ops.models import SiteDeletionRequest
from ops.services import record_audit_event
from subscriptions.gateway import (
    BillingNotConfigured,
    set_subscription_cancel_at_period_end,
)
from subscriptions.models import PlatformSubscription

from .models import Site, SiteDomain, SiteRole, SiteTheme


class SiteCreationDecision(NamedTuple):
    allowed: bool
    reason: str = ""


class SiteCreationNotAllowed(Exception):
    pass


DEFAULT_SITE_DELETION_HOLD_DAYS = 3


def site_has_subscription_exemption(site):
    return SiteRole.objects.filter(
        site=site,
        role=SiteRole.Role.SUBSCRIBER_ADMIN,
        is_active=True,
        user__is_subscription_exempt=True,
    ).exists()


def subscriber_site_creation_decision(user):
    if user.is_subscription_exempt:
        return SiteCreationDecision(True)
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
    is_exempt = locked_owner.is_subscription_exempt
    site = Site.objects.create(
        display_name=display_name,
        slug=slug,
        status=Site.Status.ACTIVE if is_exempt else Site.Status.TRIALING,
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
        status=(
            PlatformSubscription.Status.ACTIVE
            if is_exempt
            else PlatformSubscription.Status.TRIALING
        ),
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
                site_has_subscription_exemption(site)
                or (
                subscription.stripe_customer_id
                and subscription.stripe_subscription_id
                and subscription.billing_interval
                )
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


def _resume_subscription_status(subscription, *, now):
    if site_has_subscription_exemption(subscription.site):
        return PlatformSubscription.Status.ACTIVE
    if subscription.stripe_customer_id and subscription.stripe_subscription_id:
        return PlatformSubscription.Status.ACTIVE
    if subscription.trial_ends_at > now:
        return PlatformSubscription.Status.TRIALING
    raise ValidationError(
        "This trial has ended. Choose a billing plan before resuming the site."
    )


def _apply_site_and_subscription_status(*, site, subscription, status):
    subscription.status = status
    site.status = {
        PlatformSubscription.Status.TRIALING: Site.Status.TRIALING,
        PlatformSubscription.Status.ACTIVE: Site.Status.ACTIVE,
        PlatformSubscription.Status.GRACE: Site.Status.GRACE,
        PlatformSubscription.Status.SUSPENDED: Site.Status.SUSPENDED,
        PlatformSubscription.Status.CANCELED: Site.Status.CANCELED,
        PlatformSubscription.Status.ARCHIVED: Site.Status.ARCHIVED,
    }[status]


def _sync_stripe_cancel_schedule(*, subscription, cancel_at_period_end):
    if not subscription.stripe_subscription_id:
        return False
    try:
        set_subscription_cancel_at_period_end(
            subscription=subscription,
            cancel_at_period_end=cancel_at_period_end,
        )
    except BillingNotConfigured:
        return False
    except stripe.StripeError as exc:
        raise ValidationError(
            "We could not update Stripe billing right now. Please try again."
        ) from exc
    return True


@transaction.atomic
def suspend_site_access(*, site, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A suspension reason is required.")
    if not site.accepts_public_traffic:
        raise ValidationError("This site is already not live.")

    now = timezone.now()
    subscription = site.platform_subscription
    _apply_site_and_subscription_status(
        site=site,
        subscription=subscription,
        status=PlatformSubscription.Status.SUSPENDED,
    )
    subscription.suspended_at = now
    subscription.save(update_fields=("status", "suspended_at", "updated_at"))
    site.save(update_fields=("status", "updated_at"))
    record_audit_event(
        action="site.lifecycle.suspended",
        actor=actor,
        site_id=site.id,
        target=site,
        summary={"reason": reason[:200]},
        request=request,
    )
    return site


@transaction.atomic
def resume_site_access(*, site, actor, request=None):
    subscription = site.platform_subscription
    if site.accepts_public_traffic:
        return site

    now = timezone.now()
    was_canceled = subscription.status == PlatformSubscription.Status.CANCELED
    status = _resume_subscription_status(subscription, now=now)
    _apply_site_and_subscription_status(
        site=site, subscription=subscription, status=status
    )
    subscription.suspended_at = None
    if was_canceled:
        subscription.canceled_at = None
    subscription.save(
        update_fields=(
            "status",
            "suspended_at",
            "canceled_at",
            "updated_at",
        )
    )
    site.save(update_fields=("status", "updated_at"))
    record_audit_event(
        action="site.lifecycle.resumed",
        actor=actor,
        site_id=site.id,
        target=site,
        summary={"status": status},
        request=request,
    )
    return site


def site_deletion_hold_days():
    return max(
        1,
        int(
            getattr(
                settings,
                "SITE_DELETION_HOLD_DAYS",
                DEFAULT_SITE_DELETION_HOLD_DAYS,
            )
        ),
    )


@transaction.atomic
def start_site_delete_hold(*, site, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A deletion reason is required.")

    now = timezone.now()
    hold_days = site_deletion_hold_days()
    subscription = site.platform_subscription
    stripe_synced = _sync_stripe_cancel_schedule(
        subscription=subscription,
        cancel_at_period_end=True,
    )
    _apply_site_and_subscription_status(
        site=site,
        subscription=subscription,
        status=PlatformSubscription.Status.CANCELED,
    )
    subscription.suspended_at = now
    subscription.canceled_at = now
    subscription.cancel_at_period_end = True
    subscription.save(
        update_fields=(
            "status",
            "suspended_at",
            "canceled_at",
            "cancel_at_period_end",
            "updated_at",
        )
    )
    site.save(update_fields=("status", "updated_at"))

    deletion = SiteDeletionRequest.objects.filter(
        site=site,
        status__in=(
            SiteDeletionRequest.Status.REQUESTED,
            SiteDeletionRequest.Status.APPROVED,
        ),
    ).first()
    if deletion is None:
        deletion = SiteDeletionRequest.objects.create(
            site=site,
            site_id_snapshot=site.id,
            site_slug=site.slug,
            site_name=site.display_name,
            reason=reason,
            status=SiteDeletionRequest.Status.APPROVED,
            requested_by=actor,
            approved_by=actor,
            approved_at=now,
            deletion_eligible_at=now + timedelta(days=hold_days),
        )
    else:
        deletion.reason = reason
        deletion.status = SiteDeletionRequest.Status.APPROVED
        deletion.requested_by = actor
        deletion.approved_by = actor
        deletion.approved_at = now
        deletion.deletion_eligible_at = now + timedelta(days=hold_days)
        deletion.save(
            update_fields=(
                "reason",
                "status",
                "requested_by",
                "approved_by",
                "approved_at",
                "deletion_eligible_at",
            )
        )
    record_audit_event(
        action="site.lifecycle.delete_hold_started",
        actor=actor,
        site_id=site.id,
        target=deletion,
        summary={
            "hold_days": hold_days,
            "reason": reason[:200],
            "stripe_synced": stripe_synced,
        },
        request=request,
    )
    return deletion


@transaction.atomic
def cancel_site_delete_hold(*, site, actor, reason, request=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("A cancellation reason is required.")

    deletion = SiteDeletionRequest.objects.filter(
        site=site,
        status__in=(
            SiteDeletionRequest.Status.REQUESTED,
            SiteDeletionRequest.Status.APPROVED,
        ),
    ).first()
    if deletion is None:
        raise ValidationError("No pending deletion hold is active for this site.")

    subscription = site.platform_subscription
    stripe_synced = _sync_stripe_cancel_schedule(
        subscription=subscription,
        cancel_at_period_end=False,
    )

    deletion.status = SiteDeletionRequest.Status.CANCELED
    deletion.save(update_fields=("status",))
    resume_site_access(site=site, actor=actor, request=request)
    record_audit_event(
        action="site.lifecycle.delete_hold_canceled",
        actor=actor,
        site_id=site.id,
        target=deletion,
        summary={"reason": reason[:200], "stripe_synced": stripe_synced},
        request=request,
    )
    return deletion
