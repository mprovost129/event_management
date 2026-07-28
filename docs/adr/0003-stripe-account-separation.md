# ADR 0003: Separate platform billing from subscriber commerce

Status: Accepted  
Date: July 28, 2026

## Context

The platform earns one recurring SaaS subscription fee. It does not take a fee from event tickets or membership dues. Subscribers can be informal group leaders rather than registered companies, and they do not need payment processing to run free events.

The application must not accidentally become responsible for subscriber processing fees, balances, or chargebacks through an inappropriate funds flow.

## Decision

Maintain two explicit payment contexts:

1. Platform subscriptions use the platform Stripe account and a single configurable price after a fourteen-day no-card trial.
2. Ticket and membership payments use Stripe Connect direct-charge context on the subscriber's connected account with no application fee.

Stripe Connect onboarding is optional until a subscriber enables paid tickets or member dues. Use Stripe-hosted onboarding and select a supported account configuration where Stripe collects processing fees from the connected account. Confirm supported country and responsibility settings before live onboarding is enabled.

All provider identifiers are stored with their Stripe account context. Webhooks enter a durable, deduplicated inbox and drive local state idempotently. Browser redirects never prove payment success.

## Consequences

- Platform subscription revenue is cleanly separated from subscriber event/member revenue.
- Direct-charge objects must be queried and reconciled in the connected-account context.
- Connected-account readiness, disconnection, refunds, disputes, and webhook routing require operational tooling.
- A future platform transaction fee requires a new business decision and ADR rather than silently adding an application fee.

## References

- [Stripe direct charges](https://docs.stripe.com/connect/direct-charges)
- [Stripe direct-charge fee behavior](https://docs.stripe.com/connect/direct-charges-fee-payer-behavior)
- [Stripe subscriptions with Connect](https://docs.stripe.com/connect/subscriptions)
- [Stripe subscription trials](https://docs.stripe.com/billing/subscriptions/trials)
