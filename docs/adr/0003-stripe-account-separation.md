# ADR 0003: Separate platform billing from subscriber commerce

Status: Superseded by ADR 0008
Date: July 28, 2026

## Context

The platform earns one recurring SaaS subscription fee. It does not take a fee from event tickets or membership dues. Subscribers can be informal group leaders rather than registered companies, and they do not need payment processing to run free events.

The application must not accidentally become responsible for subscriber processing fees, balances, or chargebacks through an inappropriate funds flow.

## Decision

Maintain two explicit payment contexts:

1. Platform subscriptions use the platform Stripe account and one Standard feature tier, offered with monthly and yearly prices after a fourteen-day no-card trial.
2. Ticket and membership payments use Stripe Connect direct-charge context on the subscriber's connected account with no application fee.

Stripe Connect onboarding is optional until a subscriber enables paid tickets or member dues. Use Stripe-hosted onboarding with Accounts v1 controller properties equivalent to Standard behavior: `fees.payer=account`, `losses.payments=stripe`, `requirement_collection=stripe`, and `stripe_dashboard.type=full`. This gives the subscriber a full Stripe Dashboard, makes Stripe responsible for requirement collection and negative-balance liability, and makes the connected account responsible for its Stripe fees. Confirm supported countries before live onboarding is enabled; the account country remains selectable in Stripe-hosted onboarding.

All provider identifiers are stored with their Stripe account context. Webhooks enter a durable, deduplicated inbox and drive local state idempotently. Browser redirects never prove payment success.

## Consequences

- Platform subscription revenue is cleanly separated from subscriber event/member revenue.
- Direct-charge objects must be queried and reconciled in the connected-account context.
- Connected-account readiness, disconnection, refunds, disputes, and webhook routing require operational tooling.
- A future platform transaction fee requires a new business decision and ADR rather than silently adding an application fee. That decision is recorded in ADR 0008.

## References

- [Stripe direct charges](https://docs.stripe.com/connect/direct-charges)
- [Stripe direct-charge fee behavior](https://docs.stripe.com/connect/direct-charges-fee-payer-behavior)
- [Stripe subscriptions with Connect](https://docs.stripe.com/connect/subscriptions)
- [Stripe account controller properties](https://docs.stripe.com/connect/migrate-to-controller-properties)
- [Stripe-hosted onboarding](https://docs.stripe.com/connect/hosted-onboarding)
- [Stripe subscription trials](https://docs.stripe.com/billing/subscriptions/trials)
