# Stripe Sandbox Validation

Validation date: July 28, 2026

The read-only `validate_stripe_sandbox` command reached the configured US test-mode platform account. It did not create or update Stripe data.

## Passed

- Monthly price is active, test mode, USD 20.00, recurring every month, and uses `standard_monthly`.
- Yearly price is active, test mode, USD 220.00, recurring every year, and uses `standard_yearly`.
- The platform webhook destination ending in `/billing/stripe/` is enabled and contains every required platform-subscription event.
- The Connect webhook destination ending in `/commerce/stripe/connect/` is enabled and contains every event exposed and required for this sandbox configuration.
- The application uses distinct configured signing secrets for platform and Connect webhook handlers.

## Deauthorization limitation and fallback

Stripe documents `account.application.deauthorized` for Standard connected accounts, but it is not exposed in this sandbox's Workbench event selector. The application still accepts that event if it becomes available later.

As a fallback, Celery refreshes connected-account access every six hours. A temporary network, authentication, or Stripe service error is retained as an operational failure and does not disconnect the subscriber. Three consecutive permanent `account_invalid` or `resource_missing` responses mark the account disconnected, disable local commerce readiness, and create an audit event.

API inspection cannot prove possession of the endpoint signing secret; the sandbox delivery drills in `LAUNCH_CHECKLIST.md` remain required.
