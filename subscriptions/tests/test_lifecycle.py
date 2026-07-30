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
def test_delayed_older_webhook_cannot_regress_subscription_state():
    _, site, subscription = create_subscription_fixture()
    subscription.stripe_subscription_id = "sub_123"
    subscription.status = PlatformSubscription.Status.GRACE
    subscription.save()
    site.status = Site.Status.GRACE
    site.save()
    newer = int(timezone.now().timestamp())

    process_stripe_event(
        {
            "id": "evt_invoice_paid_newer",
            "type": "invoice.paid",
            "created": newer,
            "data": {"object": {"id": "in_paid", "subscription": "sub_123"}},
        }
    )
    process_stripe_event(
        {
            "id": "evt_payment_failed_older",
            "type": "invoice.payment_failed",
            "created": newer - 300,
            "data": {"object": {"id": "in_failed", "subscription": "sub_123"}},
        }
    )

    subscription.refresh_from_db()
    site.refresh_from_db()
    assert subscription.status == PlatformSubscription.Status.ACTIVE
    assert subscription.grace_ends_at is None
    assert site.status == Site.Status.ACTIVE
    assert StripeWebhookEvent.objects.filter(
        stripe_event_id="evt_payment_failed_older",
        status=StripeWebhookEvent.Status.PROCESSED,
    ).exists()


@pytest.mark.django_db
def test_paused_subscription_suspends_site_access():
    _, site, subscription = create_subscription_fixture()
    subscription.stripe_subscription_id = "sub_123"
    subscription.status = PlatformSubscription.Status.ACTIVE
    subscription.save()
    site.status = Site.Status.ACTIVE
    site.save()

    process_stripe_event(
        {
            "id": "evt_subscription_paused",
            "type": "customer.subscription.paused",
            "data": {"object": {"id": "sub_123"}},
        }
    )

    subscription.refresh_from_db()
    site.refresh_from_db()
    assert subscription.status == PlatformSubscription.Status.SUSPENDED
    assert site.status == Site.Status.SUSPENDED
    assert subscription.suspended_at is not None


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
    STRIPE_STANDARD_MONTHLY_PRICE_ID="price_monthly",
    STRIPE_STANDARD_YEARLY_PRICE_ID="price_yearly",
    STRIPE_STANDARD_MONTHLY_LOOKUP_KEY="standard_monthly",
    STRIPE_STANDARD_YEARLY_LOOKUP_KEY="standard_yearly",
)
@patch("subscriptions.gateway.stripe.checkout.Session.create")
@pytest.mark.parametrize(
    ("billing_interval", "expected_price", "expected_lookup_key"),
    (
        (
            PlatformSubscription.BillingInterval.MONTHLY,
            "price_monthly",
            "standard_monthly",
        ),
        (
            PlatformSubscription.BillingInterval.YEARLY,
            "price_yearly",
            "standard_yearly",
        ),
    ),
)
def test_checkout_preserves_trial_and_uses_selected_billing_cadence(
    mock_create, billing_interval, expected_price, expected_lookup_key
):
    owner, _, subscription = create_subscription_fixture()
    mock_create.return_value.url = "https://checkout.stripe.test/session"

    session = create_checkout_session(
        subscription=subscription,
        owner=owner,
        billing_interval=billing_interval,
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )

    assert session.url == "https://checkout.stripe.test/session"
    params = mock_create.call_args.kwargs
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": expected_price, "quantity": 1}]
    assert params["subscription_data"]["trial_period_days"] == 14
    assert params["metadata"]["platform_subscription_id"] == str(subscription.id)
    assert params["metadata"]["billing_interval"] == billing_interval
    assert params["metadata"]["lookup_key"] == expected_lookup_key


@pytest.mark.django_db
def test_checkout_is_disabled_until_platform_billing_is_configured():
    owner, _, subscription = create_subscription_fixture()

    with pytest.raises(BillingNotConfigured):
        create_checkout_session(
            subscription=subscription,
            owner=owner,
            billing_interval=PlatformSubscription.BillingInterval.MONTHLY,
            success_url="https://example.test/success",
            cancel_url="https://example.test/cancel",
        )


@pytest.mark.django_db
@override_settings(
    STRIPE_STANDARD_MONTHLY_PRICE_ID="price_monthly",
    STRIPE_STANDARD_YEARLY_PRICE_ID="price_yearly",
)
def test_checkout_webhook_persists_selected_billing_cadence():
    _, _, subscription = create_subscription_fixture()

    process_stripe_event(
        {
            "id": "evt_checkout_complete",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_123",
                    "customer": "cus_123",
                    "subscription": "sub_123",
                    "metadata": {
                        "platform_subscription_id": str(subscription.id),
                        "billing_interval": "yearly",
                        "price_id": "price_yearly",
                    },
                }
            },
        }
    )

    subscription.refresh_from_db()
    assert subscription.stripe_customer_id == "cus_123"
    assert subscription.stripe_subscription_id == "sub_123"
    assert subscription.stripe_price_id == "price_yearly"
    assert subscription.billing_interval == PlatformSubscription.BillingInterval.YEARLY


@pytest.mark.django_db
@override_settings(
    STRIPE_STANDARD_MONTHLY_PRICE_ID="price_monthly",
    STRIPE_STANDARD_YEARLY_PRICE_ID="price_yearly",
)
def test_subscription_webhook_reconciles_a_billing_cadence_change():
    _, _, subscription = create_subscription_fixture()
    subscription.stripe_subscription_id = "sub_123"
    subscription.stripe_price_id = "price_yearly"
    subscription.billing_interval = PlatformSubscription.BillingInterval.YEARLY
    subscription.save()

    process_stripe_event(
        {
            "id": "evt_subscription_updated",
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_123",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "items": {"data": [{"price": {"id": "price_monthly"}}]},
                }
            },
        }
    )

    subscription.refresh_from_db()
    assert subscription.stripe_price_id == "price_monthly"
    assert subscription.billing_interval == PlatformSubscription.BillingInterval.MONTHLY
