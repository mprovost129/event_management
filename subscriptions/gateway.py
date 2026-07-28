import math
from datetime import timedelta

import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


class BillingNotConfigured(ImproperlyConfigured):
    pass


def _configure_stripe():
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PLATFORM_PRICE_ID:
        raise BillingNotConfigured(
            "Platform billing is not available until its Stripe key and price are configured."
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(*, subscription, owner, success_url, cancel_url):
    _configure_stripe()
    params = {
        "mode": "subscription",
        "line_items": [{"price": settings.STRIPE_PLATFORM_PRICE_ID, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(subscription.id),
        "metadata": {"platform_subscription_id": str(subscription.id)},
        "subscription_data": {
            "metadata": {"platform_subscription_id": str(subscription.id)}
        },
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
