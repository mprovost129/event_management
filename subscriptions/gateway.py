import math
from datetime import timedelta
from decimal import Decimal

import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from .models import PlatformSubscription


class BillingNotConfigured(ImproperlyConfigured):
    pass


def billing_options():
    monthly_amount = Decimal(settings.STANDARD_MONTHLY_AMOUNT_CENTS) / 100
    yearly_amount = Decimal(settings.STANDARD_YEARLY_AMOUNT_CENTS) / 100
    return (
        {
            "interval": PlatformSubscription.BillingInterval.MONTHLY,
            "label": "Monthly",
            "amount": monthly_amount,
            "price_id": settings.STRIPE_STANDARD_MONTHLY_PRICE_ID,
            "lookup_key": settings.STRIPE_STANDARD_MONTHLY_LOOKUP_KEY,
            "annual_savings": Decimal("0"),
        },
        {
            "interval": PlatformSubscription.BillingInterval.YEARLY,
            "label": "Yearly",
            "amount": yearly_amount,
            "price_id": settings.STRIPE_STANDARD_YEARLY_PRICE_ID,
            "lookup_key": settings.STRIPE_STANDARD_YEARLY_LOOKUP_KEY,
            "annual_savings": (monthly_amount * 12) - yearly_amount,
        },
    )


def option_for_interval(billing_interval):
    option = next(
        (
            candidate
            for candidate in billing_options()
            if candidate["interval"] == billing_interval
        ),
        None,
    )
    if option is None:
        raise BillingNotConfigured("Choose monthly or yearly billing.")
    if not option["price_id"]:
        raise BillingNotConfigured(
            f"The {option['label'].lower()} Stripe price is not configured."
        )
    return option


def _configure_stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise BillingNotConfigured(
            "Platform billing is not available until its Stripe key is configured."
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(
    *, subscription, owner, billing_interval, success_url, cancel_url
):
    _configure_stripe()
    option = option_for_interval(billing_interval)
    metadata = {
        "platform_subscription_id": str(subscription.id),
        "billing_interval": option["interval"],
        "price_id": option["price_id"],
        "lookup_key": option["lookup_key"],
    }
    params = {
        "mode": "subscription",
        "line_items": [{"price": option["price_id"], "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(subscription.id),
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
    }
    if subscription.stripe_customer_id:
        params["customer"] = subscription.stripe_customer_id
    else:
        params["customer_email"] = owner.email

    remaining = subscription.trial_ends_at - timezone.now()
    if remaining > timedelta(0):
        params["subscription_data"]["trial_period_days"] = max(
            1, math.ceil(remaining.total_seconds() / 86400)
        )

    return stripe.checkout.Session.create(**params)


def create_portal_session(*, subscription, return_url):
    _configure_stripe()
    if not subscription.stripe_customer_id:
        raise BillingNotConfigured("No Stripe customer is linked to this subscription.")
    params = {
        "customer": subscription.stripe_customer_id,
        "return_url": return_url,
    }
    if settings.STRIPE_BILLING_PORTAL_CONFIGURATION_ID:
        params["configuration"] = settings.STRIPE_BILLING_PORTAL_CONFIGURATION_ID
    return stripe.billing_portal.Session.create(**params)


def set_subscription_cancel_at_period_end(*, subscription, cancel_at_period_end):
    if not subscription.stripe_subscription_id:
        return None
    _configure_stripe()
    return stripe.Subscription.modify(
        subscription.stripe_subscription_id,
        cancel_at_period_end=cancel_at_period_end,
    )
