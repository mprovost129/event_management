# ADR 0009: Resend production email delivery

Status: Accepted

Date: July 29, 2026

## Context

Gather HQs needs low-cost transactional and marketing email for invitations, confirmations, reminders, review requests, and newsletters. The existing Django backend is useful for local development and generic SMTP, but it cannot reliably return a provider message identifier or directly verify provider delivery events. Those capabilities are required to reconcile deliveries, suppress bounced contacts, and prove the pilot email journey.

## Decision

Use Resend as the recommended production email provider while retaining the `django` adapter for local development and provider-neutral fallback. Production selects Resend with `EMAIL_DELIVERY_BACKEND=resend` and supplies separate API and webhook secrets.

The Resend adapter sends plain-text application-owned content through the Email API, preserves one-click unsubscribe headers for marketing mail, attaches bounded operational tags, and uses the immutable outbox message UUID as a 24-hour provider idempotency key. The returned Resend email ID is stored on the outbox message.

Resend webhooks are accepted at `/communications/callbacks/resend/` and verified from the raw request body and Svix headers using the official SDK. Sent, delivered, bounce, complaint, failed, open, click, and suppression events are normalized into the existing durable callback processor. Bounces, complaints, and provider suppressions prevent later marketing sends to the affected contact.

## Consequences

- The initial pilot can use Resend's free allowance while volume remains low; paid service remains an operational decision as usage grows.
- `resend` is a pinned production dependency.
- A verified sending domain, API key, webhook signing secret, and real deliverability drill remain external launch requirements.
- SMS remains disabled and independent from this decision.
- A future email provider can implement the same delivery result and normalized callback contracts without changing campaign or outbox models.

## References

- [Resend Python sending guide](https://resend.com/docs/send-with-python)
- [Resend webhook verification](https://resend.com/docs/webhooks/verify-webhooks-requests)
- [Resend pricing](https://resend.com/docs/knowledge-base/what-is-resend-pricing)
