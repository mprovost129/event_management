import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class CommerceNotConfigured(ImproperlyConfigured):
    pass


def _configure_stripe():
    if not settings.STRIPE_SECRET_KEY:
        raise CommerceNotConfigured(
            "Stripe Connect is unavailable until the platform key is configured."
        )
    stripe.api_key = settings.STRIPE_SECRET_KEY


def create_standard_account(*, site):
    _configure_stripe()
    return stripe.Account.create(
        controller={
            "fees": {"payer": "account"},
            "losses": {"payments": "stripe"},
            "requirement_collection": "stripe",
            "stripe_dashboard": {"type": "full"},
        },
        metadata={"site_id": str(site.id), "site_slug": site.slug},
        idempotency_key=f"gather-hqs-connect-account-{site.id}",
    )


def retrieve_account(account_id):
    _configure_stripe()
    return stripe.Account.retrieve(account_id)


def create_onboarding_link(*, account_id, refresh_url, return_url):
    _configure_stripe()
    return stripe.AccountLink.create(
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
        collection_options={"fields": "eventually_due"},
    )


def create_ticket_checkout_session(*, order, line, success_url, cancel_url):
    _configure_stripe()
    metadata = {
        "commerce_kind": "ticket_order",
        "order_id": str(order.id),
        "site_id": str(order.site_id),
    }
    payment_intent_data = {"metadata": metadata}
    if order.application_fee_cents:
        payment_intent_data["application_fee_amount"] = order.application_fee_cents
    return stripe.checkout.Session.create(
        mode="payment",
        customer_email=order.purchaser.email,
        line_items=[
            {
                "price_data": {
                    "currency": order.currency,
                    "unit_amount": line.unit_amount_cents,
                    "product_data": {"name": line.description},
                },
                "quantity": line.quantity,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        expires_at=int(order.checkout_expires_at.timestamp()),
        client_reference_id=str(order.id),
        metadata=metadata,
        payment_intent_data=payment_intent_data,
        stripe_account=order.connected_account_id,
        idempotency_key=f"gather-hqs-ticket-checkout-{order.id}",
    )


def ensure_membership_price(*, plan, account_id):
    _configure_stripe()
    if plan.stripe_product_id and plan.stripe_price_id:
        return plan
    product = stripe.Product.create(
        name=plan.name,
        description=plan.description or None,
        metadata={"membership_plan_id": str(plan.id), "site_id": str(plan.site_id)},
        stripe_account=account_id,
        idempotency_key=f"gather-hqs-member-product-{plan.id}",
    )
    price = stripe.Price.create(
        product=product.id,
        currency=plan.currency,
        unit_amount=plan.amount_cents,
        recurring={"interval": plan.interval},
        metadata={"membership_plan_id": str(plan.id), "site_id": str(plan.site_id)},
        stripe_account=account_id,
        idempotency_key=f"gather-hqs-member-price-{plan.id}",
    )
    plan.stripe_product_id = product.id
    plan.stripe_price_id = price.id
    plan.save(update_fields=("stripe_product_id", "stripe_price_id", "updated_at"))
    return plan


def create_membership_checkout_session(
    *, member_subscription, email, success_url, cancel_url
):
    _configure_stripe()
    plan = ensure_membership_price(
        plan=member_subscription.plan,
        account_id=member_subscription.connected_account_id,
    )
    metadata = {
        "commerce_kind": "member_subscription",
        "member_subscription_id": str(member_subscription.id),
        "site_id": str(member_subscription.site_id),
    }
    return stripe.checkout.Session.create(
        mode="subscription",
        customer_email=email,
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        client_reference_id=str(member_subscription.id),
        metadata=metadata,
        subscription_data={"metadata": metadata},
        stripe_account=member_subscription.connected_account_id,
        idempotency_key=f"gather-hqs-member-checkout-{member_subscription.id}",
    )


def create_refund(*, refund):
    _configure_stripe()
    metadata = {
        "refund_id": str(refund.id),
        "order_id": str(refund.order_id),
        "site_id": str(refund.site_id),
    }
    refund_values = {
        "payment_intent": refund.order.stripe_payment_intent_id,
        "amount": refund.amount_cents,
        "metadata": metadata,
        "stripe_account": refund.order.connected_account_id,
        "idempotency_key": f"gather-hqs-refund-{refund.id}",
    }
    if refund.order.application_fee_cents:
        refund_values["refund_application_fee"] = True
    return stripe.Refund.create(
        **refund_values,
    )


def retrieve_checkout_session(*, session_id, account_id):
    _configure_stripe()
    return stripe.checkout.Session.retrieve(session_id, stripe_account=account_id)


def retrieve_member_subscription(*, subscription_id, account_id):
    _configure_stripe()
    return stripe.Subscription.retrieve(
        subscription_id, stripe_account=account_id, expand=["items.data"]
    )


def retrieve_event(event_id):
    _configure_stripe()
    return stripe.Event.retrieve(event_id)


def retrieve_charge(*, charge_id, account_id):
    _configure_stripe()
    return stripe.Charge.retrieve(
        charge_id, stripe_account=account_id, expand=["balance_transaction"]
    )
