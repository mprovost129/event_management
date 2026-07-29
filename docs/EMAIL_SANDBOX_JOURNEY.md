# Resend Email Sandbox Journey

This drill supplies the real-provider evidence required before Gather HQs sends pilot invitations or newsletters. Use a dedicated pilot site and normal application screens. Do not create or repair evidence directly in the database.

## Provider setup

1. Verify the Gather HQs sending domain in Resend.
2. Configure `EMAIL_DELIVERY_BACKEND=resend`, `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, and a verified `DEFAULT_FROM_EMAIL` address.
3. Add `https://gatherhqs.com/communications/callbacks/resend/` in Resend and select `email.sent`, `email.delivered`, `email.bounced`, `email.complained`, `email.failed`, `email.opened`, `email.clicked`, and `email.suppressed`.
4. Deploy and confirm `python manage.py launch_gate --json --fail-on-warning` passes.

## Real delivery evidence

1. Send an event invitation or other transactional message to an inbox you control. Confirm it arrives and its delivery callback appears in platform operations.
2. Send a newsletter test or small campaign to a consented address you control. Confirm the message contains the Gather HQs unsubscribe link and arrives only once.
3. Use that unsubscribe link and confirm later marketing excludes the contact.
4. Send to a safe provider test address or use Resend's supported test-event flow to produce a bounce, complaint, or suppression event. Confirm Gather HQs suppresses the contact. Never use an unrelated person's address for this test.
5. Compare the Gather HQs outbox provider IDs with the corresponding Resend email records.

## Evidence gate

Run:

```text
python manage.py email_sandbox_journey SITE_SLUG --json
```

The command is read-only and must report all eight checks as `true`. Retain the JSON, Resend event screenshots or exports, release identifier, sender-domain status, and test date with the launch evidence.
