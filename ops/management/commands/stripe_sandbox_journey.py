import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from contacts.models import MemberSubscription
from payments.models import (
    ConnectedAccount,
    ConnectWebhookEvent,
    MembershipPayment,
    Order,
    Refund,
    Ticket,
)
from sites.models import Site
from subscriptions.models import PlatformSubscription, StripeWebhookEvent


class Command(BaseCommand):
    help = "Check local evidence for the complete Stripe sandbox pilot journey."

    def add_arguments(self, parser):
        parser.add_argument("site_slug")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        site = Site.objects.filter(slug=options["site_slug"]).first()
        if site is None:
            raise CommandError("Pilot site not found.")

        platform = PlatformSubscription.objects.filter(site=site).first()
        connected = ConnectedAccount.objects.filter(site=site).first()
        connected_events = ConnectWebhookEvent.objects.none()
        if connected:
            connected_events = ConnectWebhookEvent.objects.filter(
                connected_account_id=connected.stripe_account_id,
                livemode=False,
                status=ConnectWebhookEvent.Status.PROCESSED,
            )

        platform_linked = bool(
            platform
            and platform.status
            in (
                PlatformSubscription.Status.TRIALING,
                PlatformSubscription.Status.ACTIVE,
            )
            and platform.stripe_customer_id
            and platform.stripe_subscription_id
            and platform.stripe_price_id
            and platform.billing_interval
        )
        platform_webhook = bool(
            platform_linked
            and StripeWebhookEvent.objects.filter(
                object_id=platform.stripe_subscription_id,
                event_type__in=(
                    "customer.subscription.created",
                    "customer.subscription.updated",
                    "customer.subscription.resumed",
                ),
                status=StripeWebhookEvent.Status.PROCESSED,
            ).exists()
        )

        refunded_order = (
            Order.objects.for_site(site)
            .filter(
                status__in=(Order.Status.PARTIALLY_REFUNDED, Order.Status.REFUNDED),
                refunds__status=Refund.Status.SUCCEEDED,
            )
            .exclude(stripe_checkout_session_id="")
            .exclude(stripe_payment_intent_id="")
            .distinct()
            .first()
        )
        payment_webhook = False
        issued_ticket = False
        refund_webhook = False
        ticket_application_fee_recorded = False
        ticket_application_fee_returned = False
        if refunded_order:
            payment_object_ids = {
                value
                for value in (
                    refunded_order.stripe_checkout_session_id,
                    refunded_order.stripe_payment_intent_id,
                    refunded_order.stripe_charge_id,
                )
                if value
            }
            payment_webhook = connected_events.filter(
                object_id__in=payment_object_ids,
                event_type__in=(
                    "checkout.session.completed",
                    "checkout.session.async_payment_succeeded",
                    "payment_intent.succeeded",
                    "charge.succeeded",
                ),
            ).exists()
            issued_ticket = Ticket.objects.filter(
                order_line__order=refunded_order
            ).exists()
            refund_ids = (
                refunded_order.refunds.filter(status=Refund.Status.SUCCEEDED)
                .exclude(stripe_refund_id__isnull=True)
                .exclude(stripe_refund_id="")
                .values_list("stripe_refund_id", flat=True)
            )
            refund_webhook = connected_events.filter(
                object_id__in=refund_ids,
                event_type__in=("refund.created", "refund.updated"),
            ).exists()
            ticket_application_fee_recorded = bool(
                refunded_order.application_fee_bps
                == settings.TICKET_APPLICATION_FEE_BPS
                and refunded_order.application_fee_cents > 0
            )
            ticket_application_fee_returned = bool(
                refunded_order.application_fee_refunded_cents > 0
            )

        membership = (
            MemberSubscription.objects.for_site(site)
            .annotate(
                paid_invoice_count=Count(
                    "payments",
                    filter=Q(payments__status=MembershipPayment.Status.PAID),
                    distinct=True,
                )
            )
            .filter(
                status__in=(
                    MemberSubscription.Status.TRIALING,
                    MemberSubscription.Status.ACTIVE,
                ),
                paid_invoice_count__gte=2,
            )
            .exclude(stripe_subscription_id__isnull=True)
            .exclude(stripe_subscription_id="")
            .first()
        )
        membership_subscription_webhook = False
        membership_renewal_webhooks = False
        if membership:
            membership_subscription_webhook = connected_events.filter(
                object_id=membership.stripe_subscription_id,
                event_type__in=(
                    "customer.subscription.created",
                    "customer.subscription.updated",
                    "customer.subscription.resumed",
                ),
            ).exists()
            invoice_ids = set(
                membership.payments.filter(status=MembershipPayment.Status.PAID)
                .values_list("stripe_invoice_id", flat=True)
                .distinct()
            )
            observed_invoice_count = (
                connected_events.filter(
                    object_id__in=invoice_ids,
                    event_type="invoice.paid",
                )
                .values("object_id")
                .distinct()
                .count()
            )
            membership_renewal_webhooks = observed_invoice_count >= 2

        checks = {
            "test_key_configured": settings.STRIPE_SECRET_KEY.startswith(
                ("sk_test_", "rk_test_")
            ),
            "platform_subscription_linked": platform_linked,
            "platform_subscription_webhook_processed": platform_webhook,
            "connected_account_ready": bool(connected and connected.commerce_ready),
            "connected_account_webhook_processed": connected_events.filter(
                event_type="account.updated"
            ).exists(),
            "paid_ticket_order_refunded": refunded_order is not None,
            "ticket_payment_webhook_processed": payment_webhook,
            "ticket_issued": issued_ticket,
            "ticket_refund_webhook_processed": refund_webhook,
            "ticket_application_fee_recorded": ticket_application_fee_recorded,
            "ticket_application_fee_returned": ticket_application_fee_returned,
            "membership_has_two_paid_invoices": membership is not None,
            "membership_subscription_webhook_processed": (
                membership_subscription_webhook
            ),
            "membership_renewal_webhooks_processed": membership_renewal_webhooks,
        }
        payload = {
            "ok": all(checks.values()),
            "site": site.slug,
            "checks": checks,
            "completed": sum(checks.values()),
            "total": len(checks),
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            self.stdout.write(
                f"Stripe sandbox journey: {payload['completed']}/{payload['total']}"
            )
            for label, passed in checks.items():
                self.stdout.write(f"[{'x' if passed else ' '}] {label}")
        if not payload["ok"]:
            raise CommandError("Stripe sandbox journey evidence is incomplete.")
