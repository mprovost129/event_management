# Implementation Status

Last updated: July 28, 2026

## Phase 0 - Foundation and decision records

Status: Technically complete; commercial placeholders remain intentionally configurable.

Completed:

- Environment and secret contract with a safe checked-in example
- Separate production and development dependency sets
- Production S3-compatible media configuration
- Container hardening and Docker Compose validation
- Request correlation and structured production logging
- Immutable audit-event foundation and migrations
- Shared-schema tenancy, background-work, and Stripe-separation ADRs
- GitHub Actions gates for linting, formatting, Django checks, migration drift, tests, deployment checks, and production image build
- Local SQLite feedback loop and authoritative PostgreSQL CI tests

Verified locally:

- Ruff lint and format checks pass
- Django system checks pass
- No model/migration drift detected
- Django production deployment checks pass with production-like placeholders
- All automated tests pass
- Python dependency consistency check passes
- Docker Compose configuration is valid

Open placeholders:

- Subscription price and live Stripe price identifier
- Email, SMS, hosting, and object-storage vendors

Next: Phase 1 - accounts, sites, tenancy, and the platform trial lifecycle.

## Phase 1 - Accounts, sites, tenancy, and platform trial

Status: Complete with live commercial values intentionally disabled until configured.

Completed:

- Email-based signup, password validation, verification emails, activation links, and safe resend behavior
- Canonical lowercase email storage with database-enforced case-insensitive uniqueness
- UUID-based subscriber sites, platform domains, themes, lifecycle states, and one-site-per-subscription relationship
- Subscriber-admin and site-manager roles with tenant-scoped permission decorators
- Shared-schema site-owned model/query foundation
- Verified subdomain resolution with request logging context and unknown-site rejection
- One-step subscriber onboarding and 14-day no-card trial creation
- Account, subscriber, and manager dashboards
- Site-manager add/remove controls for existing verified accounts
- Platform subscription, grace, suspension, cancellation, and recovery state services
- Stripe Checkout and Billing Portal boundary, with remaining trial days preserved during early conversion
- Signed Stripe webhook validation, durable deduplicated event inbox, retryable failures, and audited state changes
- Scheduled subscription-access management command
- Initial migrations, admin screens, responsive templates, and production configuration checks

Verified locally:

- Ruff lint and format checks pass
- Django system and deployment checks pass
- No model/migration drift detected
- 18 automated tests pass
- Python dependency consistency check passes

Live activation still requires:

- Subscription price and live Stripe price ID
- Stripe API and webhook secrets
- A configured Stripe Billing Portal

Next: Phase 2 - template site content, contacts, blog, recurring events, and the public calendar.
