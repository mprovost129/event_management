import io
import json
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from contacts.models import Member, MembershipPlan, MemberSubscription
from ops.management.commands.validate_stripe_sandbox import (
    CONNECT_EVENTS,
    PLATFORM_EVENTS,
)
from ops.tests.test_platform_operations import operations_fixture
from payments.models import (
    ConnectWebhookEvent,
    MembershipPayment,
    Order,
    Refund,
    Ticket,
)
from payments.services import reserve_ticket_order
from payments.tests.test_commerce import commerce_fixture
from subscriptions.models import PlatformSubscription, StripeWebhookEvent


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
@override_settings(STRIPE_SECRET_KEY="sk_test_journey")
def test_stripe_sandbox_journey_requires_complete_webhook_backed_evidence():
    _, site, connected, _, ticket_type, registration = commerce_fixture()
    output = io.StringIO()
    with pytest.raises(CommandError, match="evidence is incomplete"):
        call_command("stripe_sandbox_journey", site.slug, json=True, stdout=output)
    assert json.loads(output.getvalue())["ok"] is False

    platform = site.platform_subscription
    platform.status = PlatformSubscription.Status.ACTIVE
    platform.stripe_customer_id = "cus_platform"
    platform.stripe_subscription_id = "sub_platform"
    platform.stripe_price_id = "price_monthly"
    platform.billing_interval = PlatformSubscription.BillingInterval.MONTHLY
    platform.save()
    StripeWebhookEvent.objects.create(
        stripe_event_id="evt_platform_subscription",
        event_type="customer.subscription.updated",
        object_id="sub_platform",
        status=StripeWebhookEvent.Status.PROCESSED,
        processed_at=timezone.now(),
    )
    ConnectWebhookEvent.objects.create(
        stripe_event_id="evt_account_ready",
        connected_account_id=connected.stripe_account_id,
        event_type="account.updated",
        object_id=connected.stripe_account_id,
        status=ConnectWebhookEvent.Status.PROCESSED,
        processed_at=timezone.now(),
    )

    order, line = reserve_ticket_order(
        registration=registration, ticket_type=ticket_type
    )
    order.status = Order.Status.REFUNDED
    order.stripe_checkout_session_id = "cs_ticket"
    order.stripe_payment_intent_id = "pi_ticket"
    order.refunded_cents = order.total_cents
    order.paid_at = timezone.now()
    order.save()
    Ticket.objects.create(
        site=site,
        order_line=line,
        participant=registration.participants.get(is_primary=True),
        display_code="GHQ-EVIDENCE-1",
        status=Ticket.Status.REFUNDED,
    )
    Refund.objects.create(
        site=site,
        order=order,
        amount_cents=order.total_cents,
        status=Refund.Status.SUCCEEDED,
        stripe_refund_id="re_ticket",
        succeeded_at=timezone.now(),
    )
    for event_id, event_type, object_id in (
        ("evt_ticket_paid", "checkout.session.completed", "cs_ticket"),
        ("evt_ticket_refund", "refund.updated", "re_ticket"),
    ):
        ConnectWebhookEvent.objects.create(
            stripe_event_id=event_id,
            connected_account_id=connected.stripe_account_id,
            event_type=event_type,
            object_id=object_id,
            status=ConnectWebhookEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )

    member = Member.objects.create(site=site, contact=registration.contact)
    plan = MembershipPlan.objects.create(
        site=site,
        name="Dance club",
        amount_cents=2000,
        currency="usd",
        interval=MembershipPlan.Interval.MONTHLY,
    )
    membership = MemberSubscription.objects.create(
        site=site,
        member=member,
        plan=plan,
        status=MemberSubscription.Status.ACTIVE,
        connected_account_id=connected.stripe_account_id,
        stripe_customer_id="cus_member",
        stripe_subscription_id="sub_member",
    )
    ConnectWebhookEvent.objects.create(
        stripe_event_id="evt_member_subscription",
        connected_account_id=connected.stripe_account_id,
        event_type="customer.subscription.updated",
        object_id="sub_member",
        status=ConnectWebhookEvent.Status.PROCESSED,
        processed_at=timezone.now(),
    )
    for sequence in (1, 2):
        invoice_id = f"in_member_{sequence}"
        MembershipPayment.objects.create(
            site=site,
            member_subscription=membership,
            stripe_invoice_id=invoice_id,
            amount_due_cents=2000,
            amount_paid_cents=2000,
            currency="usd",
            status=MembershipPayment.Status.PAID,
            paid_at=timezone.now(),
        )
        ConnectWebhookEvent.objects.create(
            stripe_event_id=f"evt_{invoice_id}",
            connected_account_id=connected.stripe_account_id,
            event_type="invoice.paid",
            object_id=invoice_id,
            status=ConnectWebhookEvent.Status.PROCESSED,
            processed_at=timezone.now(),
        )

    output = io.StringIO()
    call_command("stripe_sandbox_journey", site.slug, json=True, stdout=output)
    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["completed"] == payload["total"] == 12


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
    connect_webhook = next(
        webhook for webhook in payload["webhooks"] if webhook["label"] == "connect"
    )
    assert connect_webhook["missing_events"] == []
    assert connect_webhook["recommended_missing_events"] == [
        "account.application.deauthorized"
    ]
    assert len(payload["warnings"]) == 1


@override_settings(STRIPE_SECRET_KEY="sk_live_validation")
def test_stripe_sandbox_validator_refuses_live_key_without_explicit_flag():
    with pytest.raises(CommandError, match="Refusing a non-test Stripe key"):
        call_command("validate_stripe_sandbox")
