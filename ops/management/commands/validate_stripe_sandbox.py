import json
from urllib.parse import urlsplit

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

PLATFORM_EVENTS = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
    "invoice.paid",
    "invoice.payment_failed",
}

CONNECT_EVENTS = {
    "account.updated",
    "account.application.deauthorized",
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "payment_intent.succeeded",
    "payment_intent.payment_failed",
    "charge.succeeded",
    "charge.dispute.created",
    "charge.dispute.updated",
    "charge.dispute.closed",
    "refund.created",
    "refund.updated",
    "refund.failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
    "invoice.paid",
    "invoice.payment_failed",
}


def _value(item, key, default=None):
    if hasattr(item, "get"):
        return item.get(key, default)
    return getattr(item, key, default)


def _path(url):
    return urlsplit(url).path.rstrip("/")


def _events(endpoint):
    return set(_value(endpoint, "enabled_events", []) or [])


class Command(BaseCommand):
    help = "Read and validate Stripe sandbox prices, account mode, and webhooks."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--skip-webhooks", action="store_true")
        parser.add_argument(
            "--use-system-trust",
            action="store_true",
            help="Use the operating system certificate store for this command process.",
        )
        parser.add_argument(
            "--allow-live",
            action="store_true",
            help="Explicitly allow read-only checks with a live-mode key.",
        )

    def handle(self, *args, **options):
        if options["use_system_trust"]:
            try:
                import truststore
            except ImportError as exc:
                raise CommandError(
                    "Install requirements-dev.txt to use --use-system-trust."
                ) from exc
            truststore.inject_into_ssl()
        secret_key = settings.STRIPE_SECRET_KEY
        if not secret_key:
            raise CommandError("STRIPE_SECRET_KEY is not configured.")
        test_mode = secret_key.startswith(("sk_test_", "rk_test_"))
        if not test_mode and not options["allow_live"]:
            raise CommandError(
                "Refusing a non-test Stripe key without the explicit --allow-live flag."
            )
        errors = []
        stripe.api_key = secret_key
        try:
            account = stripe.Account.retrieve()
            price_specs = (
                (
                    "monthly",
                    settings.STRIPE_STANDARD_MONTHLY_PRICE_ID,
                    settings.STRIPE_STANDARD_MONTHLY_LOOKUP_KEY,
                    settings.STANDARD_MONTHLY_AMOUNT_CENTS,
                    "month",
                ),
                (
                    "yearly",
                    settings.STRIPE_STANDARD_YEARLY_PRICE_ID,
                    settings.STRIPE_STANDARD_YEARLY_LOOKUP_KEY,
                    settings.STANDARD_YEARLY_AMOUNT_CENTS,
                    "year",
                ),
            )
            prices = []
            for label, price_id, lookup_key, amount, interval in price_specs:
                price = stripe.Price.retrieve(price_id)
                recurring = _value(price, "recurring", {}) or {}
                checks = {
                    "active": bool(_value(price, "active", False)),
                    "mode": bool(_value(price, "livemode", False)) != test_mode,
                    "currency": _value(price, "currency") == "usd",
                    "amount": _value(price, "unit_amount") == amount,
                    "lookup_key": _value(price, "lookup_key") == lookup_key,
                    "interval": _value(recurring, "interval") == interval,
                    "interval_count": _value(recurring, "interval_count") == 1,
                }
                if not all(checks.values()):
                    errors.append(f"{label} price does not match application settings")
                prices.append({"label": label, "price_id": price_id, "checks": checks})

            webhooks = []
            if not options["skip_webhooks"]:
                endpoint_list = stripe.WebhookEndpoint.list(limit=100)
                endpoints = list(_value(endpoint_list, "data", []) or [])
                for label, expected_path, required_events in (
                    ("platform", "/billing/stripe", PLATFORM_EVENTS),
                    ("connect", "/commerce/stripe/connect", CONNECT_EVENTS),
                ):
                    matches = [
                        endpoint
                        for endpoint in endpoints
                        if _path(_value(endpoint, "url", "")) == expected_path
                        and _value(endpoint, "status", "") == "enabled"
                        and bool(_value(endpoint, "livemode", False)) != test_mode
                    ]
                    if not matches:
                        errors.append(f"No enabled {label} webhook endpoint was found")
                        webhooks.append(
                            {"label": label, "found": False, "missing_events": []}
                        )
                        continue
                    enabled = set().union(*(_events(endpoint) for endpoint in matches))
                    missing = (
                        []
                        if "*" in enabled
                        else sorted(required_events.difference(enabled))
                    )
                    if missing:
                        errors.append(
                            f"{label} webhook is missing {len(missing)} event type(s)"
                        )
                    webhooks.append(
                        {
                            "label": label,
                            "found": True,
                            "endpoint_count": len(matches),
                            "missing_events": missing,
                        }
                    )
        except stripe.StripeError as exc:
            raise CommandError(f"Stripe sandbox validation failed: {exc}") from exc

        payload = {
            "ok": not errors,
            "mode": "test" if test_mode else "live",
            "account": {
                "id": _value(account, "id", ""),
                "country": _value(account, "country", ""),
            },
            "prices": prices,
            "webhooks": webhooks,
            "errors": errors,
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            self.stdout.write(
                self.style.SUCCESS("Stripe validation passed.")
                if payload["ok"]
                else self.style.ERROR("Stripe validation failed.")
            )
            for error in errors:
                self.stdout.write(self.style.ERROR(error))
        if errors:
            raise CommandError("Stripe configuration did not pass validation.")
