from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from sites.models import Site
from sites.services import create_subscriber_site
from subscriptions.gateway import BillingNotConfigured, create_checkout_session
from subscriptions.models import PlatformSubscription, StripeWebhookEvent
from subscriptions.services import process_stripe_event, synchronize_access
from users.models import User


def create_subscription_fixture():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    return owner, site, site.platform_subscription


@pytest.mark.django_db
def test_expired_trial_suspends_site_access():
    _, site, subscription = create_subscription_fixture()
    now = timezone.now()
    subscription.trial_started_at = now - timedelta(days=15)
    subscription.trial_ends_at = now - timedelta(seconds=1)
    subscription.save(update_fields=("trial_started_at", "trial_ends_at", "updated_at"))

    synchronize_access(subscription.id)

    subscription.refresh_from_db()
    site.refresh_from_db()
    assert subscription.status == PlatformSubscription.Status.SUSPENDED
    assert site.status == Site.Status.SUSPENDED
    assert subscription.suspended_at is not None


@pytest.mark.django_db
def test_payment_failure_enters_grace_and_duplicate_webhook_is_idempotent():
    _, site, subscription = create_subscription_fixture()
    subscription.stripe_subscription_id = "sub_123"
    subscription.status = PlatformSubscription.Status.ACTIVE
    subscription.save()
    site.status = Site.Status.ACTIVE
    site.save()
    event = {
        "id": "evt_payment_failed",
        "type": "invoice.payment_failed",
        "data": {"object": {"id": "in_123", "subscription": "sub_123"}},
    }

    first = process_stripe_event(event)
    first_grace_end = PlatformSubscription.objects.get(pk=subscription.id).grace_ends_at
    second = process_stripe_event(event)

    subscription.refresh_from_db()
    site.refresh_from_db()
    assert first.pk == second.pk
    assert StripeWebhookEvent.objects.count() == 1
    assert subscription.status == PlatformSubscription.Status.GRACE
    assert subscription.grace_ends_at == first_grace_end
    assert site.status == Site.Status.GRACE


@pytest.mark.django_db
def test_paid_invoice_recovers_site_from_grace():
    _, site, subscription = create_subscription_fixture()
    subscription.stripe_subscription_id = "sub_123"
    subscription.status = PlatformSubscription.Status.GRACE
    subscription.grace_ends_at = timezone.now() + timedelta(days=7)
    subscription.save()
    site.status = Site.Status.GRACE
    site.save()

    process_stripe_event(
        {
            "id": "evt_invoice_paid",
            "type": "invoice.paid",
            "data": {"object": {"id": "in_123", "subscription": "sub_123"}},
        }
    )

    subscription.refresh_from_db()
    site.refresh_from_db()
    assert subscription.status == PlatformSubscription.Status.ACTIVE
    assert subscription.grace_ends_at is None
    assert site.status == Site.Status.ACTIVE


@pytest.mark.django_db
def test_failed_webhook_is_retained_for_operations():
    event = {
        "id": "evt_unknown_subscription",
        "type": "invoice.paid",
        "data": {"object": {"id": "in_unknown", "subscription": "sub_missing"}},
    }

    with pytest.raises(PlatformSubscription.DoesNotExist):
        process_stripe_event(event)

    inbox = StripeWebhookEvent.objects.get(stripe_event_id=event["id"])
    assert inbox.status == StripeWebhookEvent.Status.FAILED
    assert inbox.error


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_example",
    STRIPE_PLATFORM_PRICE_ID="price_example",
)
@patch("subscriptions.gateway.stripe.checkout.Session.create")
def test_checkout_preserves_remaining_local_trial(mock_create):
    owner, _, subscription = create_subscription_fixture()
    mock_create.return_value.url = "https://checkout.stripe.test/session"

    session = create_checkout_session(
        subscription=subscription,
        owner=owner,
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )

    assert session.url == "https://checkout.stripe.test/session"
    params = mock_create.call_args.kwargs
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_example", "quantity": 1}]
    assert params["subscription_data"]["trial_period_days"] == 14
    assert params["metadata"]["platform_subscription_id"] == str(subscription.id)


@pytest.mark.django_db
def test_checkout_is_disabled_until_platform_billing_is_configured():
    owner, _, subscription = create_subscription_fixture()

    with pytest.raises(BillingNotConfigured):
        create_checkout_session(
            subscription=subscription,
            owner=owner,
            success_url="https://example.test/success",
            cancel_url="https://example.test/cancel",
        )
