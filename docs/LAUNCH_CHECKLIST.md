# V1 Launch Checklist

## Automated gates

- [ ] CI lint, formatting, Django checks, migration drift, PostgreSQL tests, dependency audit, and image build pass.
- [ ] `python manage.py launch_gate --json --fail-on-warning` passes on the release environment.
- [ ] `/health/live/` and `/health/ready/` are monitored externally.
- [ ] Primary onboarding-to-review journey passes on the release commit.
- [ ] Platform and Connect webhook secrets are distinct and current.
- [ ] Production email/SMS backends are not console adapters; SMS remains disabled if no vendor is selected.

## External evidence required

- [ ] Real Stripe sandbox subscription, Connect onboarding, paid ticket purchase/refund, and membership renewal complete with verified webhooks.
- [ ] Production email delivery, unsubscribe, bounce, and callback behavior are verified; SMS is either fully verified or not offered.
- [ ] The 100-concurrent-user production-like load drill passes and evidence is saved.
- [ ] Keyboard-only, screen-reader, zoom, contrast, and small-phone checks are signed off using `ACCESSIBILITY_REVIEW.md`.
- [ ] A backup restores into isolation and `post_restore_verify` plus representative UI checks pass.
- [ ] Provider outage/recovery drill succeeds without manually changing payment or delivery state.
- [ ] Privacy notice, terms, acceptable-use policy, review guidelines, retention policy, support contact, and subscriber refund responsibilities receive legal/business approval.
- [ ] DNS, TLS, object-storage CORS/access, sender DNS, monitoring destinations, and alert recipients are verified.
- [ ] Pilot group completes `PILOT_RUNBOOK.md` without database intervention.

## Go/no-go

The launch owner records the release/image identifier, migration version, backup identifier, open risks, and named approvers. Any cross-tenant defect, unreconciled money path, failed restore, missing provider signature verification, or inaccessible primary journey is a no-go.
