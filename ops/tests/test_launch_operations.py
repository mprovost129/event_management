import io
import json
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from ops.management.commands.validate_stripe_sandbox import (
    CONNECT_EVENTS,
    PLATFORM_EVENTS,
)
from ops.tests.test_platform_operations import operations_fixture
from subscriptions.models import StripeWebhookEvent


@pytest.mark.django_db
def test_restore_verification_is_read_only_and_requires_explicit_copy_confirmation():
    operations_fixture()
    with pytest.raises(CommandError, match="isolated restored database"):
        call_command("post_restore_verify")

    output = io.StringIO()
    call_command("post_restore_verify", confirm_restored_copy=True, stdout=output)
    payload = json.loads(output.getvalue())

    assert payload["ok"] is True
    assert payload["counts"]["sites"] == 1
    assert payload["counts"]["users"] == 1


@pytest.mark.django_db
def test_pilot_readiness_requires_operable_site_contact_and_published_event():
    _, site, _ = operations_fixture()
    output = io.StringIO()
    with pytest.raises(CommandError, match="not ready"):
        call_command("pilot_readiness", site.slug, stdout=output)

    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    output = io.StringIO()
    call_command("pilot_readiness", site.slug, stdout=output)
    assert json.loads(output.getvalue())["ok"] is True


@pytest.mark.django_db
def test_alert_summary_fails_external_monitor_when_webhook_processing_failed():
    StripeWebhookEvent.objects.create(
        stripe_event_id="evt_launch_alert",
        event_type="customer.subscription.updated",
        status=StripeWebhookEvent.Status.FAILED,
        error="synthetic failure",
    )
    output = io.StringIO()

    with pytest.raises(CommandError, match="require attention"):
        call_command(
            "alert_summary",
            json=True,
            fail_on_alert=True,
            stdout=output,
        )

    payload = json.loads(output.getvalue())
    assert payload["ok"] is False
    assert payload["alerts"][0]["code"] == "platform_webhook_failed"


@override_settings(
    STRIPE_SECRET_KEY="sk_test_validation",
    STRIPE_STANDARD_MONTHLY_PRICE_ID="price_monthly",
    STRIPE_STANDARD_YEARLY_PRICE_ID="price_yearly",
    STRIPE_STANDARD_MONTHLY_LOOKUP_KEY="standard_monthly",
    STRIPE_STANDARD_YEARLY_LOOKUP_KEY="standard_yearly",
    STANDARD_MONTHLY_AMOUNT_CENTS=2000,
    STANDARD_YEARLY_AMOUNT_CENTS=22000,
)
@patch("ops.management.commands.validate_stripe_sandbox.stripe.WebhookEndpoint.list")
@patch("ops.management.commands.validate_stripe_sandbox.stripe.Price.retrieve")
@patch("ops.management.commands.validate_stripe_sandbox.stripe.Account.retrieve")
def test_stripe_sandbox_validator_checks_prices_and_both_webhook_destinations(
    account_retrieve, price_retrieve, endpoint_list
):
    account_retrieve.return_value = {"id": "acct_platform", "country": "US"}
    price_retrieve.side_effect = lambda price_id: {
        "id": price_id,
        "active": True,
        "livemode": False,
        "currency": "usd",
        "unit_amount": 2000 if price_id == "price_monthly" else 22000,
        "lookup_key": (
            "standard_monthly" if price_id == "price_monthly" else "standard_yearly"
        ),
        "recurring": {
            "interval": "month" if price_id == "price_monthly" else "year",
            "interval_count": 1,
        },
    }
    endpoint_list.return_value = {
        "data": [
            {
                "url": "https://gatherhqs.com/billing/stripe/",
                "status": "enabled",
                "livemode": False,
                "enabled_events": sorted(PLATFORM_EVENTS),
            },
            {
                "url": "https://gatherhqs.com/commerce/stripe/connect/",
                "status": "enabled",
                "livemode": False,
                "enabled_events": sorted(CONNECT_EVENTS),
            },
        ]
    }
    output = io.StringIO()

    call_command("validate_stripe_sandbox", json=True, stdout=output)
    payload = json.loads(output.getvalue())

    assert payload["ok"] is True
    assert payload["mode"] == "test"
    assert all(all(price["checks"].values()) for price in payload["prices"])
    assert all(webhook["found"] for webhook in payload["webhooks"])


@override_settings(STRIPE_SECRET_KEY="sk_live_validation")
def test_stripe_sandbox_validator_refuses_live_key_without_explicit_flag():
    with pytest.raises(CommandError, match="Refusing a non-test Stripe key"):
        call_command("validate_stripe_sandbox")
