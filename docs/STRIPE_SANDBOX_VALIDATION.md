# Stripe Sandbox Validation

Validation date: July 28, 2026

The read-only `validate_stripe_sandbox` command reached the configured US test-mode platform account. It did not create or update Stripe data.

## Passed

- Monthly price is active, test mode, USD 20.00, recurring every month, and uses `standard_monthly`.
- Yearly price is active, test mode, USD 220.00, recurring every year, and uses `standard_yearly`.
- The platform webhook destination ending in `/billing/stripe/` is enabled and contains every required platform-subscription event.
- The Connect webhook destination ending in `/commerce/stripe/connect/` is enabled and contains all required events except the item below.
- The application uses distinct configured signing secrets for platform and Connect webhook handlers.

## Action required in Stripe Workbench

Add this event to the **Connected accounts** destination:

```text
account.application.deauthorized
```

Then rerun:

```text
python manage.py validate_stripe_sandbox --json --use-system-trust
```

The command must return `"ok": true`. API inspection cannot prove possession of the endpoint signing secret; the sandbox delivery drills in `LAUNCH_CHECKLIST.md` remain required.
