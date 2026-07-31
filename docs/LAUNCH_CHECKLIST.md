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
- [ ] Privacy notice, terms, acceptable-use policy, review guidelines, retention policy, support contact, and subscriber refund responsibilities receive legal/business approval.
- [ ] DNS, TLS, object-storage access, signed S3v4 logo/hero/blog URLs, sender DNS, monitoring destinations, and alert recipients are verified; AWS S3 uses a blank `AWS_S3_ENDPOINT_URL`.
- [ ] Cloudmersive key and advanced endpoint are configured; clean uploads succeed, EICAR is rejected, missing-key/outage/quota paths fail closed, the 3.5 MB free-tier cap is enforced, usage is monitored, and Cloudmersive vendor/privacy review is recorded using `CLOUDMERSIVE_SETUP.md`.
- [ ] Root, `www`, and wildcard subscriber DNS resolve to Render without disturbing Resend's sending-domain records.
- [ ] `SUPPORT_EMAIL` points to a staffed, tested mailbox on the production domain.
- [ ] Pilot group completes `PILOT_RUNBOOK.md` without database intervention.

## Go/no-go

The launch owner records the release/image identifier, migration version, backup identifier, open risks, and named approvers. Any cross-tenant defect, unreconciled money path, failed restore, missing provider signature verification, or inaccessible primary journey is a no-go.
