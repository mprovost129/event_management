# V1 Security Review

## Implemented controls

- Tenant-owned queries use explicit site scoping; staff decorators resolve role and site before tenant objects. Suspended sites freeze operational routes while the subscriber owner retains only billing, export, refund, and dashboard recovery access.
- Platform operations require a superuser. Support access is read-only, reasoned, expiring, and audited. Site deletion requires suspension, two distinct administrators, retention, and exact-slug command confirmation.
- Django CSRF, secure production cookies, HTTPS redirect/HSTS, clickjacking protection, bounded hosts, password validation, login throttling, request IDs, CSP, and Permissions Policy are configured.
- Invitation and unsubscribe capabilities are random and stored as hashes. Review and checkout capabilities are signed, site-bound, expiring, and revalidate current eligibility.
- Stripe-hosted pages collect payment details. Browser redirects do not grant paid state. Platform and Connect webhooks use separate secrets, durable idempotency records, account-context checks, and reconciliation.
- Marketing delivery rechecks consent immediately before sending. Successful or terminal outbox records remove message bodies and raw unsubscribe links.
- Public signup, verification resend, RSVP, newsletter, attendee review, ticket checkout, and membership checkout POSTs use hashed client/site Redis rate-limit keys. Forwarded client addresses are trusted only when the exact proxy count is configured.
- Production media requires durable object storage; uploads are type/size checked and images are processed. Subscriber HTML, CSS, and JavaScript are not accepted as executable content.
- CI runs lint, migration checks, PostgreSQL tests, deploy checks, a production image build, and `pip-audit` against pinned production requirements. Dependabot monitors Python, Actions, and Docker dependencies weekly.

## Release verification

Before every launch run:

```text
ruff check .
ruff format --check .
python manage.py check
python manage.py check --deploy --settings=config.settings.prod
python manage.py makemigrations --check --dry-run
pytest
pip-audit -r requirements.txt
python manage.py launch_gate --json --fail-on-warning
```

The local Windows audit may require the organization's TLS inspection root certificate; do not bypass certificate validation. CI is the authoritative vulnerability-audit environment.

## Required external review

- [ ] Verify production secret storage, least-privilege database/object-store/provider credentials, rotation ownership, and no secrets in image layers or logs.
- [ ] Test host-header and subdomain isolation, IDOR/cross-tenant access, CSRF, stored/reflected injection, upload handling, rate limits, account recovery, and administrator workflows from outside the hosting network.
- [ ] Verify Stripe, email, and SMS signatures with real sandbox callbacks, including replay, wrong-account, wrong-secret, and out-of-order cases.
- [ ] Review data inventory, retention/deletion, processor agreements, breach process, cookie use, and legal documents with qualified counsel.
- [ ] Confirm backup encryption, restore access, log retention/redaction, alert routing, and incident contacts.

Any cross-tenant access, signature bypass, payment-state elevation, secret disclosure, or failed restore is a launch blocker.
