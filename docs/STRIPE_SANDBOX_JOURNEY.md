# Stripe Sandbox Journey

This drill supplies the real-provider evidence required before Gather HQs can accept production payments. Use a dedicated pilot site and normal application screens. Do not create or repair evidence directly in the database.

## Complete the journey

1. Sign up as the pilot subscriber and complete the platform subscription Checkout using a Stripe test card.
2. Complete Stripe-hosted Connect onboarding and refresh the account until Gather HQs shows it ready for payments.
3. Publish a paid event, register a primary attendee, complete ticket Checkout, and confirm that a ticket is issued.
4. Issue a full or partial refund from the subscriber commerce screen and wait for the refund webhook to succeed.
5. Create a monthly membership plan, join through Checkout, and produce two paid invoices for the same membership subscription. If the connected account's sandbox Dashboard offers **Run simulation** for that subscription, use it to advance through the renewal; otherwise keep the evidence gate open until a second sandbox invoice is observed.
6. Confirm that neither webhook inbox has failed records and run commerce reconciliation.

## Verify recorded evidence

```text
python manage.py reconcile_commerce --site SITE_SLUG --retry-failed-events
python manage.py stripe_sandbox_journey SITE_SLUG --json
```

The evidence checker is read-only and must report all 14 checks as `true`. It requires a configured Stripe test key, correlated processed webhook records, a ready connected account, an issued and refunded ticket with its 3% application fee recorded and returned, and two distinct paid membership invoices observed through Connect webhooks.

Passing this command proves that Gather HQs recorded the normal sandbox journey. Retain Stripe Dashboard request/event links and screenshots with the release evidence because local database evidence alone does not prove endpoint ownership or browser usability.
