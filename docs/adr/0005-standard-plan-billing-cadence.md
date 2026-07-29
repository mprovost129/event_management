# ADR 0005: Offer one Standard tier with two billing cadences

Status: Accepted  
Date: July 28, 2026

## Context

Gather HQs is initially serving informal group leaders and emerging brands. The product should remain approachable and low-cost without creating feature confusion between tiers. Subscribers still need the option to pay monthly or make a discounted annual commitment.

## Decision

Offer one Standard feature tier with two USD billing cadences after the fourteen-day no-card trial:

| Cadence | Amount | Stripe price ID | Lookup key |
| --- | ---: | --- | --- |
| Monthly | $20.00 | `price_1TyGKX2dujKmWAFggUOrejZz` | `standard_monthly` |
| Yearly | $220.00 | `price_1TyGKX2dujKmWAFgx9MQuP3R` | `standard_yearly` |

Yearly billing saves $20 compared with twelve monthly payments. Both cadences grant the same features and create subscriptions on the platform Stripe account. The price identifiers, lookup keys, and display amounts remain environment-overridable so automated tests and isolated environments do not depend on production Stripe objects.

Checkout records the selected cadence in both Checkout Session and Subscription metadata. Authenticated Stripe webhooks reconcile the local price and cadence; a browser redirect does not activate access.

## Consequences

- Marketing and billing screens present cadence as a payment choice, not a feature-tier choice.
- The local subscription stores both the Stripe price ID and normalized monthly/yearly cadence.
- Price changes require new Stripe Price objects and a deliberate configuration/documentation update because Stripe Prices are immutable for amount and currency.
- Any future premium feature tier requires a separate product decision and ADR.
