# V1 Launch Checklist

## Automated gates

- [ ] CI lint, formatting, Django checks, migration drift, PostgreSQL tests, dependency audit, and image build pass.
- [ ] `python manage.py launch_gate --json --fail-on-warning` passes on the release environment.
- [ ] `/health/live/` and `/health/ready/` are monitored externally.
- [ ] Primary onboarding-to-review journey passes on the release commit.
- [ ] The pilot subscriber's in-product Pilot Launch Center shows every required item complete.
- [ ] Platform and Connect webhook secrets are distinct and current.
- [ ] Resend email delivery uses a verified sender domain, production API key, and distinct webhook signing secret; SMS remains disabled if no vendor is selected.
- [ ] The Render Blueprint is synced from the release commit; web, worker, scheduler, PostgreSQL, and Key Value are healthy, and no public pilot or real subscriber data remains on free instances.

## External evidence required

- [x] Read-only Stripe sandbox account, price, and endpoint validation completed; see `STRIPE_SANDBOX_VALIDATION.md`.
- [x] Documented unavailable Connect deauthorization selector event and implemented scheduled permanent-access-failure reconciliation fallback.
- [ ] Real Stripe sandbox subscription, Connect onboarding, paid ticket purchase/refund, and membership renewal complete; `stripe_sandbox_journey SITE_SLUG --json` passes and Stripe Dashboard evidence is retained.
- [ ] Production email delivery, unsubscribe, bounce, and callback behavior are verified; `email_sandbox_journey SITE_SLUG --json` passes. SMS is either fully verified or not offered.
- [ ] The 100-concurrent-user production-like load drill passes and evidence is saved.
- [ ] Keyboard-only, screen-reader, zoom, contrast, and small-phone checks are signed off using `ACCESSIBILITY_REVIEW.md`.
- [ ] A backup restores into isolation and `post_restore_verify` plus representative UI checks pass.
- [ ] Provider outage/recovery drill succeeds without manually changing payment or delivery state.
- [ ] Terms, Privacy, Cookies, Payments/Cancellations/Refunds, Acceptable Use, Retention, Security, and Review Guidelines receive legal/business approval.
- [ ] `LEGAL_BUSINESS_NAME`, `LEGAL_POSTAL_ADDRESS`, `LEGAL_EFFECTIVE_DATE`, governing law, venue, privacy email, and security email are final; `LEGAL_DRAFT=false`.
- [ ] Paid-event setup collects and publicly displays the subscriber's event-specific refund/cancellation policy before checkout.
- [ ] Marketing email includes the legally required sender identity and physical postal address for the initiating subscriber; SMS stays disabled until provider-level STOP/HELP and opt-out handling are proven.
- [ ] DNS, TLS, object-storage CORS/access, sender DNS, monitoring destinations, and alert recipients are verified.
- [ ] Root, `www`, and wildcard subscriber DNS resolve to Render without disturbing Resend's sending-domain records.
- [ ] `SUPPORT_EMAIL` points to a staffed, tested mailbox on the production domain.
- [ ] Pilot group completes `PILOT_RUNBOOK.md` without database intervention.

## Go/no-go

The launch owner records the release/image identifier, migration version, backup identifier, open risks, and named approvers. Any cross-tenant defect, unreconciled money path, failed restore, missing provider signature verification, or inaccessible primary journey is a no-go.
