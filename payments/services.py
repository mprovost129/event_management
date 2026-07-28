import secrets
from datetime import datetime, timedelta

from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from contacts.models import Contact, Member, MemberSubscription
from events.models import Participant, Registration
from ops.services import record_audit_event

from . import gateway
from .models import (
    ConnectedAccount,
    ConnectWebhookEvent,
    Dispute,
    FinancialTransition,
    InventoryHold,
    MembershipPayment,
    Order,
    OrderLine,
    Refund,
    Ticket,
    TicketType,
)

CHECKOUT_HOLD_MINUTES = 30
REGISTRATION_TOKEN_SALT = "payments.registration-checkout"


class CommerceUnavailable(ValidationError):
    pass


class InventoryUnavailable(ValidationError):
    pass


def _value(obj, key, default=None):
    if hasattr(obj, "get"):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _metadata(obj):
    return _value(obj, "metadata", {}) or {}


def _as_datetime(value):
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.get_current_timezone())


def registration_checkout_token(registration):
    return signing.dumps(
        {"registration_id": str(registration.id), "site_id": str(registration.site_id)},
        salt=REGISTRATION_TOKEN_SALT,
        compress=True,
    )


def registration_for_checkout_token(*, site, token):
    try:
        payload = signing.loads(
            token, salt=REGISTRATION_TOKEN_SALT, max_age=60 * CHECKOUT_HOLD_MINUTES
        )
    except signing.BadSignature:
        return None
    if payload.get("site_id") != str(site.id):
        return None
    return (
        Registration.objects.for_site(site)
        .select_related("contact", "occurrence__event")
        .prefetch_related("participants")
        .filter(
            pk=payload.get("registration_id"),
            response=Registration.Response.GOING,
            payment_status=Registration.PaymentStatus.PENDING,
        )
        .first()
    )


def _account_status(account):
    charges_enabled = bool(_value(account, "charges_enabled", False))
    payouts_enabled = bool(_value(account, "payouts_enabled", False))
    details_submitted = bool(_value(account, "details_submitted", False))
    requirements = _value(account, "requirements", {}) or {}
    due = list(_value(requirements, "currently_due", []) or [])
    disabled_reason = _value(requirements, "disabled_reason", "") or ""
    if charges_enabled and payouts_enabled:
        status = ConnectedAccount.Status.READY
    elif disabled_reason or (details_submitted and due):
        status = ConnectedAccount.Status.RESTRICTED
    else:
        status = ConnectedAccount.Status.PENDING
    return status, charges_enabled, payouts_enabled, details_submitted, due


@transaction.atomic
def synchronize_connected_account(account, *, site=None):
    account_id = _value(account, "id", "")
    connected = (
        ConnectedAccount.objects.select_for_update()
        .filter(stripe_account_id=account_id)
        .first()
    )
    if connected is None:
        if site is None:
            return None
        connected = ConnectedAccount(site=site, stripe_account_id=account_id)
    status, charges, payouts, details, due = _account_status(account)
    connected.status = status
    connected.country = (_value(account, "country", "") or "").upper()
    connected.charges_enabled = charges
    connected.payouts_enabled = payouts
    connected.details_submitted = details
    connected.requirements_due = due
    connected.last_synced_at = timezone.now()
    connected.disconnected_at = None
    connected.save()
    return connected


def start_connected_account(*, site):
    existing = ConnectedAccount.objects.filter(site=site).first()
    if existing:
        return existing
    account = gateway.create_standard_account(site=site)
    connected = synchronize_connected_account(account, site=site)
    record_audit_event(
        action="commerce.connected_account.created",
        site_id=site.id,
        target=connected,
        summary={"status": connected.status},
    )
    return connected


def refresh_connected_account(connected):
    return synchronize_connected_account(
        gateway.retrieve_account(connected.stripe_account_id), site=connected.site
    )


def require_commerce_ready(site):
    connected = ConnectedAccount.objects.filter(site=site).first()
    if connected is None or not connected.commerce_ready:
        raise CommerceUnavailable(
            "Stripe onboarding must be complete before accepting payments."
        )
    return connected


def ticket_inventory(ticket_type, *, now=None):
    now = now or timezone.now()
    sold = (
        OrderLine.objects.filter(
            ticket_type=ticket_type,
            order__status__in=(
                Order.Status.PAID,
                Order.Status.PARTIALLY_REFUNDED,
                Order.Status.REFUNDED,
                Order.Status.DISPUTED,
            ),
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    held = (
        InventoryHold.objects.filter(
            ticket_type=ticket_type,
            status=InventoryHold.Status.HELD,
            expires_at__gt=now,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    return {
        "sold": sold,
        "held": held,
        "remaining": max(0, ticket_type.quantity - sold - held),
    }


@transaction.atomic
def reserve_ticket_order(*, registration, ticket_type):
    connected = require_commerce_ready(registration.site)
    registration = (
        Registration.objects.select_for_update()
        .select_related("contact", "occurrence")
        .get(pk=registration.pk)
    )
    if registration.payment_status != Registration.PaymentStatus.PENDING:
        raise CommerceUnavailable("This registration is not awaiting payment.")
    participants = list(
        registration.participants.filter(status=Participant.Status.ACTIVE).order_by(
            "-is_primary", "created_at"
        )
    )
    quantity = len(participants)
    if quantity < 1:
        raise CommerceUnavailable("This registration has no active participants.")
    ticket_type = TicketType.objects.select_for_update().get(
        pk=ticket_type.pk, occurrence=registration.occurrence, site=registration.site
    )
    if not ticket_type.sales_are_open():
        raise InventoryUnavailable("Ticket sales are not open for that ticket type.")
    if quantity > ticket_type.max_per_order:
        raise InventoryUnavailable("The participant count exceeds the per-order limit.")
    inventory = ticket_inventory(ticket_type)
    confirmed = Participant.objects.filter(
        registration__occurrence=registration.occurrence,
        registration__payment_status__in=(
            Registration.PaymentStatus.NOT_REQUIRED,
            Registration.PaymentStatus.PAID,
        ),
        status=Participant.Status.ACTIVE,
    ).count()
    other_holds = (
        InventoryHold.objects.filter(
            ticket_type__occurrence=registration.occurrence,
            status=InventoryHold.Status.HELD,
            expires_at__gt=timezone.now(),
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    capacity_remaining = (
        registration.occurrence.capacity - confirmed - other_holds
        if registration.occurrence.capacity is not None
        else quantity
    )
    if inventory["remaining"] < quantity or capacity_remaining < quantity:
        raise InventoryUnavailable(
            "There are not enough tickets remaining for every participant."
        )

    expires_at = timezone.now() + timedelta(minutes=CHECKOUT_HOLD_MINUTES)
    total = ticket_type.amount_cents * quantity
    order = Order.objects.create(
        site=registration.site,
        occurrence=registration.occurrence,
        registration=registration,
        purchaser=registration.contact,
        connected_account_id=connected.stripe_account_id,
        currency=registration.site.currency,
        subtotal_cents=total,
        total_cents=total,
        checkout_expires_at=expires_at,
    )
    line = OrderLine.objects.create(
        order=order,
        ticket_type=ticket_type,
        description=f"{registration.occurrence.event.title} - {ticket_type.name}",
        unit_amount_cents=ticket_type.amount_cents,
        quantity=quantity,
        line_total_cents=total,
    )
    InventoryHold.objects.create(
        site=registration.site,
        ticket_type=ticket_type,
        order=order,
        quantity=quantity,
        expires_at=expires_at,
    )
    FinancialTransition.objects.create(
        site=registration.site,
        order=order,
        event_type="order.created",
        new_status=Order.Status.PENDING,
        details={"quantity": quantity, "total_cents": total},
    )
    return order, line


def attach_checkout_session(*, order, line, success_url, cancel_url):
    try:
        session = gateway.create_ticket_checkout_session(
            order=order, line=line, success_url=success_url, cancel_url=cancel_url
        )
    except Exception:
        FinancialTransition.objects.create(
            site=order.site,
            order=order,
            event_type="checkout.session.create_uncertain",
            previous_status=Order.Status.PENDING,
            new_status=Order.Status.PENDING,
        )
        raise
    order.stripe_checkout_session_id = _value(session, "id", "")
    order.save(update_fields=("stripe_checkout_session_id", "updated_at"))
    return session


def _ticket_code():
    return secrets.token_hex(5).upper()


@transaction.atomic
def mark_order_paid(
    order_id, *, stripe_object=None, event_id="", event_type="payment.succeeded"
):
    order = (
        Order.objects.select_for_update()
        .select_related("registration")
        .prefetch_related("registration__participants", "lines")
        .get(pk=order_id)
    )
    if order.status in (
        Order.Status.PAID,
        Order.Status.PARTIALLY_REFUNDED,
        Order.Status.REFUNDED,
        Order.Status.DISPUTED,
    ):
        if stripe_object:
            changed = []
            if (
                _value(stripe_object, "object", "") == "checkout.session"
                and not order.stripe_checkout_session_id
            ):
                order.stripe_checkout_session_id = _value(stripe_object, "id", "")
                changed.append("stripe_checkout_session_id")
            if not order.stripe_payment_intent_id:
                payment_intent = _value(stripe_object, "payment_intent", "")
                if _value(stripe_object, "object", "") == "payment_intent":
                    payment_intent = _value(stripe_object, "id", "")
                if payment_intent:
                    order.stripe_payment_intent_id = payment_intent
                    changed.append("stripe_payment_intent_id")
            if changed:
                order.save(update_fields=(*changed, "updated_at"))
        return order
    previous = order.status
    payment_intent = (
        _value(stripe_object, "payment_intent", "") if stripe_object else ""
    )
    if _value(stripe_object, "object", "") == "payment_intent":
        payment_intent = _value(stripe_object, "id", "")
    order.stripe_payment_intent_id = payment_intent or order.stripe_payment_intent_id
    order.stripe_checkout_session_id = (
        _value(stripe_object, "id", "")
        if _value(stripe_object, "object", "") == "checkout.session"
        else order.stripe_checkout_session_id
    )
    latest_charge = _value(stripe_object, "latest_charge", "") if stripe_object else ""
    order.stripe_charge_id = latest_charge or order.stripe_charge_id
    order.status = Order.Status.PAID
    order.paid_at = order.paid_at or timezone.now()
    order.save()
    InventoryHold.objects.filter(order=order).update(
        status=InventoryHold.Status.CONVERTED
    )
    registration = order.registration
    registration.payment_status = Registration.PaymentStatus.PAID
    registration.save(update_fields=("payment_status", "updated_at"))
    line = order.lines.first()
    participants = registration.participants.filter(status=Participant.Status.ACTIVE)
    for participant in participants:
        if Ticket.objects.filter(participant=participant).exists():
            continue
        code = _ticket_code()
        while Ticket.objects.filter(display_code=code).exists():
            code = _ticket_code()
        Ticket.objects.create(
            site=order.site, order_line=line, participant=participant, display_code=code
        )
    FinancialTransition.objects.create(
        site=order.site,
        order=order,
        event_type=event_type,
        previous_status=previous,
        new_status=order.status,
        stripe_event_id=event_id,
    )
    from .messaging import queue_ticket_receipt

    queue_ticket_receipt(order)
    return order


@transaction.atomic
def fail_order(order_id, *, event_id="", event_type="payment.failed", expired=False):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status != Order.Status.PENDING:
        return order
    previous = order.status
    order.status = Order.Status.EXPIRED if expired else Order.Status.FAILED
    order.save(update_fields=("status", "updated_at"))
    InventoryHold.objects.filter(order=order, status=InventoryHold.Status.HELD).update(
        status=InventoryHold.Status.RELEASED
    )
    FinancialTransition.objects.create(
        site=order.site,
        order=order,
        event_type=event_type,
        previous_status=previous,
        new_status=order.status,
        stripe_event_id=event_id,
    )
    return order


def release_expired_holds(*, now=None):
    now = now or timezone.now()
    order_ids = list(
        InventoryHold.objects.filter(
            status=InventoryHold.Status.HELD, expires_at__lte=now
        ).values_list("order_id", flat=True)
    )
    for order_id in order_ids:
        fail_order(order_id, event_type="inventory.hold.expired", expired=True)
    return len(order_ids)


@transaction.atomic
def prepare_refund(*, order, amount_cents, reason, actor):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status not in (
        Order.Status.PAID,
        Order.Status.PARTIALLY_REFUNDED,
        Order.Status.DISPUTED,
    ):
        raise CommerceUnavailable("Only a paid order can be refunded.")
    if amount_cents < 1 or amount_cents > order.total_cents - order.refunded_cents:
        raise CommerceUnavailable(
            "The refund amount is outside the refundable balance."
        )
    refund = Refund.objects.create(
        site=order.site,
        order=order,
        amount_cents=amount_cents,
        reason=reason,
        created_by=actor,
    )
    FinancialTransition.objects.create(
        site=order.site,
        order=order,
        refund=refund,
        event_type="refund.requested",
        new_status=Refund.Status.PENDING,
        details={"amount_cents": amount_cents},
    )
    return refund


def submit_refund(refund):
    provider_refund = gateway.create_refund(refund=refund)
    refund.stripe_refund_id = _value(provider_refund, "id", "")
    refund.save(update_fields=("stripe_refund_id", "updated_at"))
    apply_refund_object(provider_refund, event_type="refund.created")
    return refund


@transaction.atomic
def apply_refund_object(
    stripe_refund, *, event_id="", event_type="refund.updated", account_id=""
):
    metadata = _metadata(stripe_refund)
    refund = None
    if metadata.get("refund_id"):
        refund = (
            Refund.objects.select_for_update().filter(pk=metadata["refund_id"]).first()
        )
    if refund is None:
        refund = (
            Refund.objects.select_for_update()
            .filter(stripe_refund_id=_value(stripe_refund, "id", ""))
            .first()
        )
    if refund is None:
        return None
    order = Order.objects.select_for_update().get(pk=refund.order_id)
    if account_id and order.connected_account_id != account_id:
        raise ValidationError(
            "Webhook connected-account context does not match the refund order."
        )
    previous_refund = refund.status
    provider_status = _value(stripe_refund, "status", "pending")
    status_map = {
        "succeeded": Refund.Status.SUCCEEDED,
        "pending": Refund.Status.PENDING,
        "failed": Refund.Status.FAILED,
        "canceled": Refund.Status.CANCELED,
    }
    refund.status = status_map.get(provider_status, refund.status)
    refund.stripe_refund_id = _value(stripe_refund, "id", "") or refund.stripe_refund_id
    refund.failure_reason = _value(stripe_refund, "failure_reason", "") or ""
    if (
        refund.status == Refund.Status.SUCCEEDED
        and previous_refund != Refund.Status.SUCCEEDED
    ):
        refund.succeeded_at = timezone.now()
        order.refunded_cents += refund.amount_cents
        previous_order = order.status
        if order.refunded_cents >= order.total_cents:
            order.status = Order.Status.REFUNDED
            Ticket.objects.filter(order_line__order=order).update(
                status=Ticket.Status.REFUNDED
            )
            order.registration.payment_status = Registration.PaymentStatus.REFUNDED
            order.registration.save(update_fields=("payment_status", "updated_at"))
        else:
            order.status = Order.Status.PARTIALLY_REFUNDED
        order.save(update_fields=("refunded_cents", "status", "updated_at"))
    else:
        previous_order = order.status
    refund.save()
    if previous_refund != refund.status:
        FinancialTransition.objects.create(
            site=order.site,
            order=order,
            refund=refund,
            event_type=event_type,
            previous_status=previous_refund,
            new_status=refund.status,
            stripe_event_id=event_id,
            details={
                "order_status": order.status,
                "previous_order_status": previous_order,
            },
        )
    return refund


@transaction.atomic
def start_member_subscription(*, site, plan, first_name, last_name, email, account_id):
    contact = (
        Contact.objects.select_for_update()
        .filter(site=site, normalized_email=email)
        .first()
    )
    if contact is None:
        contact = Contact.objects.create(
            site=site, first_name=first_name, last_name=last_name, email=email
        )
    member, _ = Member.objects.get_or_create(site=site, contact=contact)
    return MemberSubscription.objects.create(
        site=site,
        member=member,
        plan=plan,
        connected_account_id=account_id,
    )


def attach_member_checkout(*, member_subscription, success_url, cancel_url):
    session = gateway.create_membership_checkout_session(
        member_subscription=member_subscription,
        email=member_subscription.member.contact.email,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    member_subscription.stripe_checkout_session_id = _value(session, "id", "")
    member_subscription.save(update_fields=("stripe_checkout_session_id", "updated_at"))
    return session


def _member_subscription_from_object(stripe_object):
    metadata = _metadata(stripe_object)
    local_id = metadata.get("member_subscription_id")
    if local_id:
        found = MemberSubscription.objects.filter(pk=local_id).first()
        if found:
            return found
    provider_id = _value(stripe_object, "id", "")
    if _value(stripe_object, "object", "") == "subscription":
        return MemberSubscription.objects.filter(
            stripe_subscription_id=provider_id
        ).first()
    provider_id = _value(stripe_object, "subscription", "")
    return MemberSubscription.objects.filter(stripe_subscription_id=provider_id).first()


@transaction.atomic
def apply_member_subscription(stripe_object, *, account_id=""):
    subscription = _member_subscription_from_object(stripe_object)
    if subscription is None:
        return None
    subscription = MemberSubscription.objects.select_for_update().get(
        pk=subscription.pk
    )
    if account_id and subscription.connected_account_id != account_id:
        raise ValidationError(
            "Webhook connected-account context does not match the member subscription."
        )
    previous_status = subscription.status
    object_type = _value(stripe_object, "object", "")
    if object_type == "checkout.session":
        subscription.stripe_customer_id = _value(stripe_object, "customer", "") or ""
        subscription.stripe_subscription_id = (
            _value(stripe_object, "subscription", "") or None
        )
    else:
        subscription.stripe_subscription_id = _value(stripe_object, "id", "")
        subscription.stripe_customer_id = _value(stripe_object, "customer", "") or ""
        provider_status = _value(stripe_object, "status", "")
        status_map = {
            "incomplete": MemberSubscription.Status.INCOMPLETE,
            "incomplete_expired": MemberSubscription.Status.EXPIRED,
            "trialing": MemberSubscription.Status.TRIALING,
            "active": MemberSubscription.Status.ACTIVE,
            "past_due": MemberSubscription.Status.PAST_DUE,
            "unpaid": MemberSubscription.Status.PAST_DUE,
            "canceled": MemberSubscription.Status.CANCELED,
            "paused": MemberSubscription.Status.PAST_DUE,
        }
        subscription.status = status_map.get(provider_status, subscription.status)
        subscription.current_period_starts_at = _as_datetime(
            _value(stripe_object, "current_period_start")
        )
        subscription.current_period_ends_at = _as_datetime(
            _value(stripe_object, "current_period_end")
        )
        subscription.cancel_at_period_end = bool(
            _value(stripe_object, "cancel_at_period_end", False)
        )
        subscription.canceled_at = _as_datetime(_value(stripe_object, "canceled_at"))
    subscription.save()
    if (
        subscription.status == MemberSubscription.Status.ACTIVE
        and previous_status != MemberSubscription.Status.ACTIVE
    ):
        from .messaging import queue_membership_receipt

        queue_membership_receipt(subscription)
    return subscription


@transaction.atomic
def apply_member_invoice(stripe_object, *, paid, account_id=""):
    provider_id = _value(stripe_object, "subscription", "")
    if not provider_id:
        details = _value(stripe_object, "subscription_details", {}) or {}
        provider_id = _value(details, "subscription", "")
    subscription = (
        MemberSubscription.objects.select_for_update()
        .filter(stripe_subscription_id=provider_id)
        .first()
    )
    if subscription is None:
        return None
    if account_id and subscription.connected_account_id != account_id:
        raise ValidationError(
            "Webhook connected-account context does not match the member subscription."
        )
    subscription.status = (
        MemberSubscription.Status.ACTIVE if paid else MemberSubscription.Status.PAST_DUE
    )
    subscription.save(update_fields=("status", "updated_at"))
    MembershipPayment.objects.update_or_create(
        stripe_invoice_id=_value(stripe_object, "id", ""),
        defaults={
            "site": subscription.site,
            "member_subscription": subscription,
            "amount_due_cents": _value(stripe_object, "amount_due", 0) or 0,
            "amount_paid_cents": _value(stripe_object, "amount_paid", 0) or 0,
            "currency": (
                _value(stripe_object, "currency", subscription.plan.currency)
                or subscription.plan.currency
            ).lower(),
            "status": (
                MembershipPayment.Status.PAID
                if paid
                else MembershipPayment.Status.FAILED
            ),
            "paid_at": (
                _as_datetime(
                    _value(
                        _value(stripe_object, "status_transitions", {}) or {}, "paid_at"
                    )
                )
                if paid
                else None
            ),
        },
    )
    return subscription


def _order_from_object(stripe_object):
    metadata = _metadata(stripe_object)
    if metadata.get("order_id"):
        return Order.objects.filter(pk=metadata["order_id"]).first()
    object_type = _value(stripe_object, "object", "")
    if object_type == "checkout.session":
        return Order.objects.filter(
            stripe_checkout_session_id=_value(stripe_object, "id", "")
        ).first()
    if object_type == "payment_intent":
        return Order.objects.filter(
            stripe_payment_intent_id=_value(stripe_object, "id", "")
        ).first()
    if object_type == "charge":
        query = Q(stripe_charge_id=_value(stripe_object, "id", ""))
        payment_intent_id = _value(stripe_object, "payment_intent", "")
        if payment_intent_id:
            query |= Q(stripe_payment_intent_id=payment_intent_id)
        return Order.objects.filter(query).first()
    return None


@transaction.atomic
def apply_charge(stripe_object, *, account_id=""):
    order = _order_from_object(stripe_object)
    if order is None:
        return None
    if account_id and order.connected_account_id != account_id:
        raise ValidationError(
            "Webhook connected-account context does not match the order."
        )
    order = Order.objects.select_for_update().get(pk=order.pk)
    order.stripe_charge_id = _value(stripe_object, "id", "") or order.stripe_charge_id
    balance_transaction = _value(stripe_object, "balance_transaction", "")
    if isinstance(balance_transaction, str):
        order.stripe_balance_transaction_id = balance_transaction
    elif balance_transaction:
        order.stripe_balance_transaction_id = _value(balance_transaction, "id", "")
        order.stripe_fee_cents = _value(balance_transaction, "fee")
        order.stripe_net_cents = _value(balance_transaction, "net")
    order.save()
    return order


@transaction.atomic
def apply_dispute(stripe_object, *, event_type, account_id=""):
    payment_intent_id = _value(stripe_object, "payment_intent", "")
    charge_id = _value(stripe_object, "charge", "")
    if not payment_intent_id and not charge_id:
        return None
    order = (
        Order.objects.select_for_update()
        .filter(
            Q(stripe_payment_intent_id=payment_intent_id)
            | Q(stripe_charge_id=charge_id)
        )
        .first()
    )
    if order is None:
        return None
    if account_id and order.connected_account_id != account_id:
        raise ValidationError(
            "Webhook connected-account context does not match the order."
        )
    evidence = _value(stripe_object, "evidence_details", {}) or {}
    dispute, _ = Dispute.objects.update_or_create(
        stripe_dispute_id=_value(stripe_object, "id", ""),
        defaults={
            "site": order.site,
            "order": order,
            "amount_cents": _value(stripe_object, "amount", 0),
            "status": _value(stripe_object, "status", "unknown"),
            "reason": _value(stripe_object, "reason", "") or "",
            "due_by": _as_datetime(_value(evidence, "due_by")),
        },
    )
    previous = order.status
    if event_type != "charge.dispute.closed" or dispute.status == "lost":
        order.status = Order.Status.DISPUTED
    elif dispute.status == "won":
        order.status = Order.Status.PAID
    order.save(update_fields=("status", "updated_at"))
    FinancialTransition.objects.create(
        site=order.site,
        order=order,
        event_type=event_type,
        previous_status=previous,
        new_status=order.status,
        details={
            "dispute_id": dispute.stripe_dispute_id,
            "dispute_status": dispute.status,
        },
    )
    return dispute


def process_connect_event(event):
    event_id = event["id"]
    event_type = event["type"]
    stripe_object = event["data"]["object"]
    account_id = event.get("account", "")
    inbox, _ = ConnectWebhookEvent.objects.get_or_create(
        stripe_event_id=event_id,
        defaults={
            "connected_account_id": account_id,
            "event_type": event_type,
            "object_id": _value(stripe_object, "id", ""),
            "livemode": bool(event.get("livemode", False)),
        },
    )
    if inbox.status == ConnectWebhookEvent.Status.PROCESSED:
        return inbox
    try:
        with transaction.atomic():
            inbox = ConnectWebhookEvent.objects.select_for_update().get(pk=inbox.pk)
            if inbox.status == ConnectWebhookEvent.Status.PROCESSED:
                return inbox
            inbox.attempts += 1
            _apply_connect_event(event_type, stripe_object, account_id, event_id)
            inbox.status = ConnectWebhookEvent.Status.PROCESSED
            inbox.error = ""
            inbox.processed_at = timezone.now()
            inbox.save()
    except Exception as exc:
        inbox.refresh_from_db()
        inbox.status = ConnectWebhookEvent.Status.FAILED
        inbox.error = str(exc)[:2000]
        inbox.attempts += 1
        inbox.save(update_fields=("status", "error", "attempts"))
        raise
    return inbox


def _apply_connect_event(event_type, stripe_object, account_id, event_id):
    if event_type == "account.updated":
        synchronize_connected_account(stripe_object)
        return
    if event_type == "account.application.deauthorized":
        ConnectedAccount.objects.filter(stripe_account_id=account_id).update(
            status=ConnectedAccount.Status.DISCONNECTED,
            charges_enabled=False,
            payouts_enabled=False,
            disconnected_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return
    order = _order_from_object(stripe_object)
    if order and order.connected_account_id != account_id:
        raise ValidationError(
            "Webhook connected-account context does not match the order."
        )
    if event_type in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        if _metadata(stripe_object).get("commerce_kind") == "member_subscription":
            apply_member_subscription(stripe_object, account_id=account_id)
        elif order and (
            event_type == "checkout.session.async_payment_succeeded"
            or _value(stripe_object, "payment_status", "") == "paid"
        ):
            mark_order_paid(
                order.id,
                stripe_object=stripe_object,
                event_id=event_id,
                event_type=event_type,
            )
        return
    if event_type == "payment_intent.succeeded" and order:
        mark_order_paid(
            order.id,
            stripe_object=stripe_object,
            event_id=event_id,
            event_type=event_type,
        )
        return
    if event_type == "charge.succeeded":
        apply_charge(stripe_object, account_id=account_id)
        return
    if (
        event_type
        in (
            "checkout.session.expired",
            "checkout.session.async_payment_failed",
            "payment_intent.payment_failed",
        )
        and order
    ):
        fail_order(
            order.id,
            event_id=event_id,
            event_type=event_type,
            expired=event_type == "checkout.session.expired",
        )
        return
    if event_type in ("refund.created", "refund.updated", "refund.failed"):
        apply_refund_object(
            stripe_object,
            event_id=event_id,
            event_type=event_type,
            account_id=account_id,
        )
        return
    if event_type.startswith("customer.subscription."):
        apply_member_subscription(stripe_object, account_id=account_id)
        return
    if event_type in ("invoice.paid", "invoice.payment_failed"):
        apply_member_invoice(
            stripe_object,
            paid=event_type == "invoice.paid",
            account_id=account_id,
        )
        return
    if event_type in (
        "charge.dispute.created",
        "charge.dispute.updated",
        "charge.dispute.closed",
    ):
        apply_dispute(stripe_object, event_type=event_type, account_id=account_id)


def commerce_summary(site):
    orders = Order.objects.for_site(site)
    subscriptions = MemberSubscription.objects.for_site(site)
    gross = (
        orders.filter(
            status__in=(
                Order.Status.PAID,
                Order.Status.PARTIALLY_REFUNDED,
                Order.Status.REFUNDED,
                Order.Status.DISPUTED,
            )
        ).aggregate(total=Sum("total_cents"))["total"]
        or 0
    )
    refunds = orders.aggregate(total=Sum("refunded_cents"))["total"] or 0
    fees = orders.aggregate(total=Sum("stripe_fee_cents"))["total"] or 0
    member_dues = (
        MembershipPayment.objects.for_site(site)
        .filter(status=MembershipPayment.Status.PAID)
        .aggregate(total=Sum("amount_paid_cents"))["total"]
        or 0
    )
    return {
        "ticket_gross_cents": gross,
        "stripe_fees_cents": fees,
        "refunds_cents": refunds,
        "ticket_net_cents": gross - refunds - fees,
        "member_dues_cents": member_dues,
        "active_members": subscriptions.filter(
            status=MemberSubscription.Status.ACTIVE
        ).count(),
        "past_due_members": subscriptions.filter(
            status=MemberSubscription.Status.PAST_DUE
        ).count(),
    }


def reconcile_site_commerce(site):
    """Refresh recoverable provider state without using webhooks as a sole source."""
    results = {"account": 0, "orders": 0, "member_subscriptions": 0, "errors": []}
    connected = ConnectedAccount.objects.filter(site=site).first()
    if connected is None:
        return results
    try:
        refresh_connected_account(connected)
        results["account"] = 1
    except Exception as exc:
        results["errors"].append(f"account: {exc}")
    for order in (
        Order.objects.for_site(site)
        .filter(status=Order.Status.PENDING)
        .exclude(stripe_checkout_session_id="")
    ):
        try:
            provider = gateway.retrieve_checkout_session(
                session_id=order.stripe_checkout_session_id,
                account_id=order.connected_account_id,
            )
            if _value(provider, "payment_status", "") == "paid":
                mark_order_paid(
                    order.id, stripe_object=provider, event_type="reconciliation"
                )
            elif _value(provider, "status", "") == "expired":
                fail_order(order.id, event_type="reconciliation", expired=True)
            results["orders"] += 1
        except Exception as exc:
            results["errors"].append(f"order {order.id}: {exc}")
    for order in (
        Order.objects.for_site(site)
        .filter(
            status__in=(Order.Status.PAID, Order.Status.PARTIALLY_REFUNDED),
            stripe_fee_cents__isnull=True,
        )
        .exclude(stripe_charge_id="")
    ):
        try:
            charge = gateway.retrieve_charge(
                charge_id=order.stripe_charge_id,
                account_id=order.connected_account_id,
            )
            apply_charge(charge, account_id=order.connected_account_id)
        except Exception as exc:
            results["errors"].append(f"order fee {order.id}: {exc}")
    for local in (
        MemberSubscription.objects.for_site(site)
        .exclude(stripe_subscription_id__isnull=True)
        .exclude(stripe_subscription_id="")
    ):
        try:
            provider = gateway.retrieve_member_subscription(
                subscription_id=local.stripe_subscription_id,
                account_id=local.connected_account_id,
            )
            apply_member_subscription(provider)
            results["member_subscriptions"] += 1
        except Exception as exc:
            results["errors"].append(f"member subscription {local.id}: {exc}")
    return results


def retry_failed_connect_events(*, limit=100):
    retried = 0
    errors = []
    inboxes = ConnectWebhookEvent.objects.filter(
        status=ConnectWebhookEvent.Status.FAILED
    ).order_by("received_at")[:limit]
    for inbox in inboxes:
        try:
            event = gateway.retrieve_event(inbox.stripe_event_id)
            process_connect_event(event)
            retried += 1
        except Exception as exc:
            errors.append(f"{inbox.stripe_event_id}: {exc}")
    return {"retried": retried, "errors": errors}
