# ADR 0008: Three-percent paid-ticket application fee

Status: Accepted
Date: July 28, 2026

## Context

Gather HQs charges subscribers for the site and management product, but paid-ticket commerce also creates ongoing payment, reconciliation, refund, dispute, reporting, and support costs. The initial audience is price-sensitive and often runs informal groups, so the fee must remain simple, predictable, and materially below mainstream ticket-marketplace pricing.

## Decision

Collect a 3% application fee on paid event ticket orders. The fee is calculated in integer minor currency units from the order total, rounded to the nearest minor unit, and snapshotted on the order as 300 basis points. It is deducted from the subscriber's connected-account proceeds through Stripe Connect `payment_intent_data.application_fee_amount`; it is not added to the attendee's displayed ticket total.

Monthly and yearly member dues remain exempt from the application fee during the pilot. Free events never incur a fee. Stripe processing fees, refunds, disputes, and chargebacks remain the connected account's responsibility.

Full and partial ticket refunds set `refund_application_fee=true`, returning the application fee to the connected account proportionally. Gather HQs records the cumulative returned portion with the order so subscriber net and platform-fee reporting remain understandable and auditable.

The percentage is deployment-configurable as `TICKET_APPLICATION_FEE_BPS`, with 300 as the product default and zero as a safe rollback setting. Every order preserves the fee rate and amount applied when checkout began, so a future pricing change cannot rewrite historical orders.

## Consequences

- Subscribers see the percentage before enabling paid tickets and can see the fee on each order and in aggregate reporting.
- Attendees see the ticket price selected by the organizer without a separate Gather HQs surcharge.
- Member-dues Checkout continues without `application_fee_percent`.
- Direct charges and their application fees remain scoped to the existing connected-account money flow.
- Supported launch countries must permit the platform to collect Connect application fees; Stripe documents restrictions for some cross-border configurations, including certain Brazilian connected accounts.
- Legal and tax review must cover the platform's application-fee revenue before live launch.

## References

- [Stripe direct charges and application fees](https://docs.stripe.com/connect/direct-charges)
- [Stripe refund application fees](https://docs.stripe.com/api/refunds/create)
- [Stripe Connect pricing](https://stripe.com/connect/pricing)
