from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ops.services import record_audit_event
from sites.models import Site

from .models import PlatformSubscription, StripeWebhookEvent

SITE_STATUS_BY_SUBSCRIPTION = {
    PlatformSubscription.Status.TRIALING: Site.Status.TRIALING,
    PlatformSubscription.Status.ACTIVE: Site.Status.ACTIVE,
    PlatformSubscription.Status.GRACE: Site.Status.GRACE,
    PlatformSubscription.Status.SUSPENDED: Site.Status.SUSPENDED,
    PlatformSubscription.Status.CANCELED: Site.Status.CANCELED,
    PlatformSubscription.Status.ARCHIVED: Site.Status.ARCHIVED,
}


def _as_datetime(unix_timestamp):
    if not unix_timestamp:
        return None
    return datetime.fromtimestamp(unix_timestamp, tz=timezone.get_current_timezone())


def _set_status(subscription, status, *, now=None, audit_action=None):
    now = now or timezone.now()
    changed = subscription.status != status
    subscription.status = status
    if status == PlatformSubscription.Status.SUSPENDED:
        subscription.suspended_at = now
    elif status in {
        PlatformSubscription.Status.ACTIVE,
        PlatformSubscription.Status.TRIALING,
        PlatformSubscription.Status.GRACE,
    }:
        subscription.suspended_at = None

    subscription.site.status = SITE_STATUS_BY_SUBSCRIPTION[status]
    subscription.site.save(update_fields=("status", "updated_at"))
    subscription.save()

    if changed and audit_action:
        record_audit_event(
            action=audit_action,
            site_id=subscription.site_id,
            target=subscription,
            summary={"status": status},
        )


@transaction.atomic
def synchronize_access(subscription_id, *, now=None):
    now = now or timezone.now()
    subscription = (
        PlatformSubscription.objects.select_for_update()
        .select_related("site")
        .get(pk=subscription_id)
    )
    if (
        subscription.status == PlatformSubscription.Status.TRIALING
        and subscription.trial_ends_at <= now
    ):
        _set_status(
            subscription,
            PlatformSubscription.Status.SUSPENDED,
            now=now,
            audit_action="subscription.trial_expired",
        )
    elif (
        subscription.status == PlatformSubscription.Status.GRACE
        and subscription.grace_ends_at
        and subscription.grace_ends_at <= now
    ):
        _set_status(
            subscription,
            PlatformSubscription.Status.SUSPENDED,
            now=now,
            audit_action="subscription.grace_expired",
        )
    return subscription


def process_stripe_event(event):
    event_id = event["id"]
    event_type = event["type"]
    stripe_object = event["data"]["object"]
    object_id = stripe_object.get("id", "")

    inbox, created = StripeWebhookEvent.objects.get_or_create(
        stripe_event_id=event_id,
        defaults={"event_type": event_type, "object_id": object_id},
    )
    if not created and inbox.status == StripeWebhookEvent.Status.PROCESSED:
        return inbox

    try:
        with transaction.atomic():
            inbox = StripeWebhookEvent.objects.select_for_update().get(pk=inbox.pk)
            if inbox.status == StripeWebhookEvent.Status.PROCESSED:
                return inbox
            _apply_stripe_event(event_type, stripe_object)
            inbox.status = StripeWebhookEvent.Status.PROCESSED
            inbox.error = ""
            inbox.processed_at = timezone.now()
            inbox.save(update_fields=("status", "error", "processed_at"))
    except Exception as exc:
        inbox.status = StripeWebhookEvent.Status.FAILED
        inbox.error = str(exc)[:2000]
        inbox.save(update_fields=("status", "error"))
        raise
    return inbox


def _apply_stripe_event(event_type, stripe_object):
    if event_type == "checkout.session.completed":
        metadata = stripe_object.get("metadata", {})
        subscription_id = metadata.get("platform_subscription_id")
        if not subscription_id:
            return
        subscription = PlatformSubscription.objects.select_for_update().get(
            pk=subscription_id
        )
        subscription.stripe_customer_id = stripe_object.get("customer") or ""
        subscription.stripe_subscription_id = (
            stripe_object.get("subscription") or subscription.stripe_subscription_id
        )
        subscription.save(
            update_fields=(
                "stripe_customer_id",
                "stripe_subscription_id",
                "updated_at",
            )
        )
        return

    stripe_subscription_id = stripe_object.get("subscription")
    if event_type.startswith("customer.subscription."):
        stripe_subscription_id = stripe_object.get("id")
    if not stripe_subscription_id:
        return

    subscription = (
        PlatformSubscription.objects.select_for_update()
        .select_related("site")
        .get(stripe_subscription_id=stripe_subscription_id)
    )
    now = timezone.now()

    if event_type in {"invoice.paid", "customer.subscription.resumed"}:
        subscription.grace_ends_at = None
        _set_status(
            subscription,
            PlatformSubscription.Status.ACTIVE,
            now=now,
            audit_action="subscription.activated",
        )
    elif event_type == "invoice.payment_failed":
        subscription.grace_ends_at = now + timedelta(
            days=settings.SUBSCRIPTION_GRACE_DAYS
        )
        _set_status(
            subscription,
            PlatformSubscription.Status.GRACE,
            now=now,
            audit_action="subscription.payment_failed",
        )
    elif event_type == "customer.subscription.deleted":
        subscription.canceled_at = now
        _set_status(
            subscription,
            PlatformSubscription.Status.CANCELED,
            now=now,
            audit_action="subscription.canceled",
        )
    elif event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
    }:
        provider_status = stripe_object.get("status")
        subscription.cancel_at_period_end = bool(
            stripe_object.get("cancel_at_period_end")
        )
        subscription.current_period_ends_at = _as_datetime(
            stripe_object.get("current_period_end")
        )
        if provider_status == "active":
            status = PlatformSubscription.Status.ACTIVE
        elif provider_status == "trialing":
            status = PlatformSubscription.Status.TRIALING
        elif provider_status in {"past_due", "unpaid"}:
            subscription.grace_ends_at = subscription.grace_ends_at or (
                now + timedelta(days=settings.SUBSCRIPTION_GRACE_DAYS)
            )
            status = PlatformSubscription.Status.GRACE
        elif provider_status in {"canceled", "paused"}:
            status = PlatformSubscription.Status.SUSPENDED
        else:
            subscription.save()
            return
        _set_status(
            subscription,
            status,
            now=now,
            audit_action="subscription.provider_status_changed",
        )
