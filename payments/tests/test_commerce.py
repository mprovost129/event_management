from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import stripe
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from attendance.services import set_check_in
from contacts.models import MembershipPlan, MemberSubscription
from events.models import Event, Registration
from events.registration import save_public_response
from events.reporting import occurrence_metrics
from events.services import create_event_series
from payments.gateway import create_refund, create_ticket_checkout_session
from payments.models import (
    ConnectedAccount,
    ConnectWebhookEvent,
    Dispute,
    InventoryHold,
    MembershipPayment,
    Order,
    Refund,
    Ticket,
    TicketType,
)
from payments.services import (
    apply_refund_object,
    attach_member_checkout,
    commerce_summary,
    mark_order_paid,
    prepare_refund,
    process_connect_event,
    refresh_connected_account,
    registration_checkout_token,
    reserve_ticket_order,
    start_member_subscription,
    synchronize_connected_account,
    ticket_inventory,
)
from payments.tasks import reconcile_connected_accounts
from sites.services import create_subscriber_site
from users.models import User


def commerce_fixture(*, capacity=10, ticket_quantity=10, guests=1):
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
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    starts_at = timezone.now() + timedelta(days=7)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Friday dance",
            "slug": "friday-dance",
            "description": "Dance night",
            "host_name": "Pat",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": guests,
        },
        first_start=starts_at,
        first_end=starts_at + timedelta(hours=2),
        capacity=capacity,
    )
    occurrence = event.occurrences.get()
    connected = ConnectedAccount.objects.create(
        site=site,
        stripe_account_id="acct_site",
        status=ConnectedAccount.Status.READY,
        charges_enabled=True,
        payouts_enabled=True,
        details_submitted=True,
    )
    ticket_type = TicketType.objects.create(
        site=site,
        occurrence=occurrence,
        name="General admission",
        amount_cents=1500,
        currency="usd",
        quantity=ticket_quantity,
        max_per_order=5,
    )
    registration, _ = save_public_response(
        site=site,
        occurrence=occurrence,
        response=Registration.Response.GOING,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
        guests=([{"first_name": "Sam", "last_name": "Guest"}] if guests else []),
    )
    return owner, site, connected, occurrence, ticket_type, registration


@pytest.mark.django_db
def test_paid_rsvp_waits_for_payment_before_capacity_or_check_in():
    owner, _, _, occurrence, _, registration = commerce_fixture(capacity=2)
    participant = registration.participants.get(is_primary=True)

    assert registration.payment_status == Registration.PaymentStatus.PENDING
    assert occurrence_metrics(occurrence)["participants"] == 0
    with pytest.raises(ValidationError, match="Only active going"):
        set_check_in(participant=participant, actor=owner, checked_in=True)


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_example")
@patch("payments.gateway.stripe.checkout.Session.create")
def test_direct_ticket_checkout_collects_snapshotted_platform_fee(mock_create):
    _, _, _, _, ticket_type, registration = commerce_fixture()
    order, line = reserve_ticket_order(
        registration=registration, ticket_type=ticket_type
    )
    mock_create.return_value = SimpleNamespace(id="cs_123", url="https://stripe.test")

    create_ticket_checkout_session(
        order=order,
        line=line,
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )

    params = mock_create.call_args.kwargs
    assert params["stripe_account"] == "acct_site"
    assert params["mode"] == "payment"
    assert params["metadata"]["order_id"] == str(order.id)
    assert "application_fee_amount" not in params
    assert "payment_intent_data" in params
    assert order.application_fee_bps == 300
    assert order.application_fee_cents == 90
    assert params["payment_intent_data"]["application_fee_amount"] == 90


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_example", TICKET_APPLICATION_FEE_BPS=0)
@patch("payments.gateway.stripe.checkout.Session.create")
def test_ticket_platform_fee_can_be_disabled_without_changing_checkout(mock_create):
    _, _, _, _, ticket_type, registration = commerce_fixture()
    order, line = reserve_ticket_order(
        registration=registration, ticket_type=ticket_type
    )
    mock_create.return_value = SimpleNamespace(id="cs_123", url="https://stripe.test")

    create_ticket_checkout_session(
        order=order,
        line=line,
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )

    assert order.application_fee_cents == 0
    assert (
        "application_fee_amount"
        not in mock_create.call_args.kwargs["payment_intent_data"]
    )


@pytest.mark.django_db
def test_payment_webhook_converts_hold_creates_one_ticket_per_participant_and_dedupes():
    _, _, _, occurrence, ticket_type, registration = commerce_fixture(capacity=2)
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)
    event = {
        "id": "evt_checkout_paid",
        "type": "checkout.session.completed",
        "account": "acct_site",
        "livemode": False,
        "data": {
            "object": {
                "id": "cs_paid",
                "object": "checkout.session",
                "payment_status": "paid",
                "payment_intent": "pi_paid",
                "metadata": {
                    "commerce_kind": "ticket_order",
                    "order_id": str(order.id),
                },
            }
        },
    }

    first = process_connect_event(event)
    second = process_connect_event(event)
    process_connect_event(
        {
            "id": "evt_checkout_expired_late",
            "type": "checkout.session.expired",
            "account": "acct_site",
            "livemode": False,
            "data": {"object": event["data"]["object"]},
        }
    )

    order.refresh_from_db()
    registration.refresh_from_db()
    assert first.pk == second.pk
    assert ConnectWebhookEvent.objects.count() == 2
    assert order.status == Order.Status.PAID
    assert order.stripe_payment_intent_id == "pi_paid"
    assert registration.payment_status == Registration.PaymentStatus.PAID
    assert Ticket.objects.filter(order_line__order=order).count() == 2
    assert (
        InventoryHold.objects.get(order=order).status == InventoryHold.Status.CONVERTED
    )
    assert occurrence_metrics(occurrence)["participants"] == 2
    assert ticket_inventory(ticket_type)["sold"] == 2


@pytest.mark.django_db
def test_webhook_rejects_mismatched_connected_account_context():
    _, _, _, _, ticket_type, registration = commerce_fixture()
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)

    with pytest.raises(ValidationError, match="context"):
        process_connect_event(
            {
                "id": "evt_wrong_account",
                "type": "payment_intent.succeeded",
                "account": "acct_other",
                "livemode": False,
                "data": {
                    "object": {
                        "id": "pi_wrong",
                        "object": "payment_intent",
                        "metadata": {"order_id": str(order.id)},
                    }
                },
            }
        )

    assert (
        ConnectWebhookEvent.objects.get(stripe_event_id="evt_wrong_account").status
        == ConnectWebhookEvent.Status.FAILED
    )
    order.refresh_from_db()
    assert order.status == Order.Status.PENDING


@pytest.mark.django_db
def test_full_refund_is_idempotent_and_preserves_financial_history():
    owner, _, _, _, ticket_type, registration = commerce_fixture()
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)
    mark_order_paid(
        order.id,
        stripe_object={"object": "payment_intent", "id": "pi_paid"},
    )
    order.refresh_from_db()
    refund = prepare_refund(
        order=order,
        amount_cents=order.total_cents,
        reason="Event canceled",
        actor=owner,
    )
    provider_refund = {
        "id": "re_full",
        "status": "succeeded",
        "metadata": {"refund_id": str(refund.id), "order_id": str(order.id)},
    }

    apply_refund_object(provider_refund, event_id="evt_refund_1")
    apply_refund_object(provider_refund, event_id="evt_refund_2")

    order.refresh_from_db()
    refund.refresh_from_db()
    registration.refresh_from_db()
    assert refund.status == Refund.Status.SUCCEEDED
    assert order.status == Order.Status.REFUNDED
    assert order.refunded_cents == order.total_cents
    assert order.application_fee_refunded_cents == order.application_fee_cents
    assert registration.payment_status == Registration.PaymentStatus.REFUNDED
    assert not Ticket.objects.filter(
        order_line__order=order, status=Ticket.Status.VALID
    ).exists()
    assert order.financial_history.count() >= 3


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_example")
@patch("payments.gateway.stripe.checkout.Session.create")
@patch("payments.gateway.stripe.Price.create")
@patch("payments.gateway.stripe.Product.create")
def test_member_dues_checkout_and_webhooks_stay_in_connected_account(
    mock_product, mock_price, mock_checkout
):
    _, site, _, _, _, _ = commerce_fixture()
    plan = MembershipPlan.objects.create(
        site=site,
        name="Dance club",
        amount_cents=2000,
        currency="usd",
        interval=MembershipPlan.Interval.MONTHLY,
    )
    local = start_member_subscription(
        site=site,
        plan=plan,
        first_name="Jo",
        last_name="Member",
        email="jo@example.com",
        account_id="acct_site",
    )
    mock_product.return_value = SimpleNamespace(id="prod_member")
    mock_price.return_value = SimpleNamespace(id="price_member")
    mock_checkout.return_value = SimpleNamespace(
        id="cs_member", url="https://stripe.test"
    )

    attach_member_checkout(
        member_subscription=local,
        success_url="https://example.test/success",
        cancel_url="https://example.test/cancel",
    )

    checkout_params = mock_checkout.call_args.kwargs
    assert checkout_params["stripe_account"] == "acct_site"
    assert checkout_params["mode"] == "subscription"
    assert "application_fee_percent" not in checkout_params["subscription_data"]
    process_connect_event(
        {
            "id": "evt_member_checkout",
            "type": "checkout.session.completed",
            "account": "acct_site",
            "livemode": False,
            "data": {
                "object": {
                    "id": "cs_member",
                    "object": "checkout.session",
                    "customer": "cus_member",
                    "subscription": "sub_member",
                    "metadata": {
                        "commerce_kind": "member_subscription",
                        "member_subscription_id": str(local.id),
                    },
                }
            },
        }
    )
    process_connect_event(
        {
            "id": "evt_member_active",
            "type": "customer.subscription.updated",
            "account": "acct_site",
            "livemode": False,
            "data": {
                "object": {
                    "id": "sub_member",
                    "object": "subscription",
                    "customer": "cus_member",
                    "status": "active",
                    "metadata": {"member_subscription_id": str(local.id)},
                }
            },
        }
    )
    local.refresh_from_db()
    assert local.stripe_subscription_id == "sub_member"
    assert local.status == MemberSubscription.Status.ACTIVE

    process_connect_event(
        {
            "id": "evt_member_invoice_paid",
            "type": "invoice.paid",
            "account": "acct_site",
            "livemode": False,
            "data": {
                "object": {
                    "id": "in_member",
                    "object": "invoice",
                    "subscription": "sub_member",
                    "amount_due": 2000,
                    "amount_paid": 2000,
                    "currency": "usd",
                    "status_transitions": {"paid_at": int(timezone.now().timestamp())},
                }
            },
        }
    )
    payment = MembershipPayment.objects.get(stripe_invoice_id="in_member")
    assert payment.status == MembershipPayment.Status.PAID
    assert payment.amount_paid_cents == 2000


@pytest.mark.django_db
def test_connected_account_readiness_and_disconnect_follow_provider_state():
    _, site, connected, _, _, _ = commerce_fixture()
    synchronize_connected_account(
        {
            "id": connected.stripe_account_id,
            "country": "US",
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": True,
            "requirements": {
                "currently_due": ["individual.verification.document"],
                "disabled_reason": "requirements.past_due",
            },
        }
    )
    connected.refresh_from_db()
    assert connected.status == ConnectedAccount.Status.RESTRICTED
    assert not connected.commerce_ready

    process_connect_event(
        {
            "id": "evt_deauthorized",
            "type": "account.application.deauthorized",
            "account": connected.stripe_account_id,
            "livemode": False,
            "data": {"object": {"id": "ca_123"}},
        }
    )
    connected.refresh_from_db()
    assert connected.status == ConnectedAccount.Status.DISCONNECTED
    assert connected.disconnected_at is not None


@pytest.mark.django_db
@patch("payments.gateway.retrieve_account")
def test_reconciliation_disconnects_after_three_permanent_account_failures(
    retrieve_account,
):
    _, _, connected, _, _, _ = commerce_fixture()
    retrieve_account.side_effect = stripe.InvalidRequestError(
        "No such account", param="id", code="resource_missing"
    )

    for expected_failures in (1, 2):
        result = reconcile_connected_accounts()
        connected.refresh_from_db()
        assert result == {"refreshed": 0, "failed": 1}
        assert connected.sync_failure_count == expected_failures
        assert connected.permanent_sync_failure_count == expected_failures
        assert connected.status == ConnectedAccount.Status.READY

    result = reconcile_connected_accounts()
    connected.refresh_from_db()

    assert result == {"refreshed": 0, "failed": 1}
    assert connected.sync_failure_count == 3
    assert connected.permanent_sync_failure_count == 3
    assert connected.status == ConnectedAccount.Status.DISCONNECTED
    assert connected.disconnected_at is not None
    assert not connected.charges_enabled
    assert not connected.payouts_enabled


@pytest.mark.django_db
@patch("payments.gateway.retrieve_account")
def test_transient_account_sync_failures_do_not_disconnect(retrieve_account):
    _, _, connected, _, _, _ = commerce_fixture()
    retrieve_account.side_effect = stripe.APIConnectionError("Temporary outage")

    for _ in range(3):
        with pytest.raises(stripe.APIConnectionError):
            refresh_connected_account(connected)

    connected.refresh_from_db()
    assert connected.sync_failure_count == 3
    assert connected.permanent_sync_failure_count == 0
    assert connected.status == ConnectedAccount.Status.READY
    assert connected.disconnected_at is None


@pytest.mark.django_db
@patch("payments.gateway.retrieve_account")
def test_transient_failure_resets_permanent_disconnect_streak(retrieve_account):
    _, _, connected, _, _, _ = commerce_fixture()
    permanent = stripe.InvalidRequestError(
        "No such account", param="id", code="resource_missing"
    )
    retrieve_account.side_effect = [
        permanent,
        stripe.APIConnectionError("Temporary outage"),
        permanent,
        permanent,
    ]

    for _ in range(4):
        with pytest.raises(stripe.StripeError):
            refresh_connected_account(connected)

    connected.refresh_from_db()
    assert connected.sync_failure_count == 4
    assert connected.permanent_sync_failure_count == 2
    assert connected.status == ConnectedAccount.Status.READY


@pytest.mark.django_db
def test_payment_failure_releases_inventory_without_confirming_registration():
    _, _, _, _, ticket_type, registration = commerce_fixture()
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)

    process_connect_event(
        {
            "id": "evt_payment_failed",
            "type": "payment_intent.payment_failed",
            "account": "acct_site",
            "livemode": False,
            "data": {
                "object": {
                    "id": "pi_failed",
                    "object": "payment_intent",
                    "metadata": {"order_id": str(order.id)},
                }
            },
        }
    )

    order.refresh_from_db()
    registration.refresh_from_db()
    assert order.status == Order.Status.FAILED
    assert registration.payment_status == Registration.PaymentStatus.PENDING
    assert (
        InventoryHold.objects.get(order=order).status == InventoryHold.Status.RELEASED
    )
    assert ticket_inventory(ticket_type)["held"] == 0


@pytest.mark.django_db
def test_dispute_is_visible_and_updates_order_financial_history():
    _, _, _, _, ticket_type, registration = commerce_fixture()
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)
    mark_order_paid(
        order.id,
        stripe_object={
            "object": "payment_intent",
            "id": "pi_paid",
            "latest_charge": "ch_paid",
        },
    )

    process_connect_event(
        {
            "id": "evt_dispute_created",
            "type": "charge.dispute.created",
            "account": "acct_site",
            "livemode": False,
            "data": {
                "object": {
                    "id": "dp_123",
                    "object": "dispute",
                    "charge": "ch_paid",
                    "payment_intent": "pi_paid",
                    "amount": 3000,
                    "status": "needs_response",
                    "reason": "fraudulent",
                    "evidence_details": {},
                }
            },
        }
    )

    order.refresh_from_db()
    dispute = Dispute.objects.get(stripe_dispute_id="dp_123")
    assert order.status == Order.Status.DISPUTED
    assert dispute.status == "needs_response"
    assert order.financial_history.filter(event_type="charge.dispute.created").exists()


@pytest.mark.django_db
def test_charge_webhook_records_provider_fee_details_when_available():
    _, _, _, _, ticket_type, registration = commerce_fixture()
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)
    mark_order_paid(
        order.id,
        stripe_object={"object": "payment_intent", "id": "pi_fee"},
    )

    process_connect_event(
        {
            "id": "evt_charge_succeeded",
            "type": "charge.succeeded",
            "account": "acct_site",
            "livemode": False,
            "data": {
                "object": {
                    "id": "ch_fee",
                    "object": "charge",
                    "payment_intent": "pi_fee",
                    "balance_transaction": {
                        "id": "txn_fee",
                        "fee": 207,
                        "net": 2793,
                        "fee_details": [
                            {"type": "stripe_fee", "amount": 117},
                            {"type": "application_fee", "amount": 90},
                        ],
                    },
                }
            },
        }
    )

    order.refresh_from_db()
    assert order.stripe_charge_id == "ch_fee"
    assert order.stripe_fee_cents == 117
    assert order.stripe_net_cents == 2793


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_example")
@patch("payments.gateway.stripe.Refund.create")
def test_ticket_refund_returns_platform_fee_proportionally(mock_create):
    owner, site, _, _, ticket_type, registration = commerce_fixture()
    order, _ = reserve_ticket_order(registration=registration, ticket_type=ticket_type)
    mark_order_paid(
        order.id,
        stripe_object={"object": "payment_intent", "id": "pi_paid"},
    )
    order.refresh_from_db()
    refund = prepare_refund(
        order=order,
        amount_cents=order.total_cents // 2,
        reason="Partial refund",
        actor=owner,
    )
    mock_create.return_value = {
        "id": "re_partial",
        "status": "pending",
        "metadata": {"refund_id": str(refund.id)},
    }

    create_refund(refund=refund)
    params = mock_create.call_args.kwargs
    assert params["refund_application_fee"] is True
    assert params["stripe_account"] == "acct_site"

    apply_refund_object(
        {
            "id": "re_partial",
            "status": "succeeded",
            "metadata": {"refund_id": str(refund.id)},
        }
    )
    order.refresh_from_db()
    assert order.application_fee_cents == 90
    assert order.application_fee_refunded_cents == 45
    assert commerce_summary(site)["platform_fee_net_cents"] == 45


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_example")
@patch("payments.gateway.stripe.Account.create")
def test_new_connect_account_uses_standard_fee_payer_configuration(mock_create):
    _, site, connected, _, _, _ = commerce_fixture()
    connected.delete()
    mock_create.return_value = {
        "id": "acct_standard",
        "country": "US",
        "charges_enabled": False,
        "payouts_enabled": False,
        "details_submitted": False,
        "requirements": {"currently_due": []},
    }

    from payments.services import start_connected_account

    created = start_connected_account(site=site)

    assert created.stripe_account_id == "acct_standard"
    controller = mock_create.call_args.kwargs["controller"]
    assert controller["fees"]["payer"] == "account"
    assert controller["losses"]["payments"] == "stripe"
    assert controller["requirement_collection"] == "stripe"
    assert controller["stripe_dashboard"]["type"] == "full"
    assert "type" not in mock_create.call_args.kwargs


@pytest.mark.django_db
@override_settings(STRIPE_CONNECT_WEBHOOK_SECRET="whsec_connect")
@patch("payments.views.process_connect_event")
@patch("payments.views.stripe.Webhook.construct_event")
def test_connect_webhook_verifies_signature_before_processing(
    mock_construct, mock_process, client
):
    event = {
        "id": "evt_signed",
        "type": "account.updated",
        "account": "acct_site",
        "data": {"object": {"id": "acct_site"}},
    }
    mock_construct.return_value = event

    response = client.post(
        "/commerce/stripe/connect/",
        data=b"{}",
        content_type="application/json",
        headers={"Stripe-Signature": "signed-header"},
    )

    assert response.status_code == 200
    mock_construct.assert_called_once()
    assert mock_construct.call_args.kwargs["secret"] == "whsec_connect"
    mock_process.assert_called_once_with(event)


@pytest.mark.django_db
def test_commerce_dashboard_and_edit_surfaces_render_for_subscriber_admin(client):
    owner, site, _, _, ticket_type, _ = commerce_fixture()
    plan = MembershipPlan.objects.create(
        site=site,
        name="Annual club",
        amount_cents=22000,
        currency="usd",
        interval=MembershipPlan.Interval.YEARLY,
    )
    client.force_login(owner)

    dashboard = client.get(reverse("payments:manage", kwargs={"site_id": site.id}))
    ticket_edit = client.get(
        reverse(
            "payments:ticket_type_edit",
            kwargs={"site_id": site.id, "ticket_type_id": ticket_type.id},
        )
    )
    plan_edit = client.get(
        reverse(
            "payments:membership_plan_edit",
            kwargs={"site_id": site.id, "plan_id": plan.id},
        )
    )

    assert dashboard.status_code == 200
    assert "Payments &amp; memberships" in dashboard.content.decode()
    assert ticket_edit.status_code == 200
    assert plan_edit.status_code == 200


@pytest.mark.django_db
def test_ticket_setup_explains_when_stripe_is_not_ready(client):
    owner, site, connected, occurrence, _, _ = commerce_fixture()
    connected.delete()
    client.force_login(owner)

    response = client.get(
        reverse(
            "payments:ticket_type_create",
            kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
        )
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "Stripe setup needed" in content
    assert "Connect Stripe before creating paid tickets" in content
    assert "Open payment setup" in content


@pytest.mark.django_db
def test_new_membership_plan_form_renders_for_ready_connected_account(client):
    owner, site, _, _, _, _ = commerce_fixture()
    client.force_login(owner)

    response = client.get(reverse("payments:membership_plan_create", args=(site.id,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Create a membership plan" in content
    assert "Stripe ready" in content
    assert "RSVPs remain separate" in content


@pytest.mark.django_db
def test_ticket_checkout_only_shows_options_that_cover_the_whole_party(client):
    _, site, _, occurrence, ticket_type, registration = commerce_fixture(guests=1)
    TicketType.objects.create(
        site=site,
        occurrence=occurrence,
        name="Single admission only",
        amount_cents=1000,
        currency="usd",
        quantity=10,
        max_per_order=1,
    )
    token = registration_checkout_token(registration)

    response = client.get(
        reverse("payments:ticket_checkout", kwargs={"token": token}),
        headers={"host": "boot-scooters.localhost"},
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert ticket_type.name in content
    assert "Single admission only" not in content
    assert "$30.00 total" in content
    assert "2 tickets" in content
    assert "Payment handled by Stripe" in content
