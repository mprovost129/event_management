# Implementation Status

Last updated: July 28, 2026

## Phase 0 - Foundation and decision records

Status: Complete. Commercial infrastructure values remain intentionally configurable.

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

- Email, SMS, hosting, and object-storage vendors

Completed next milestone: Phase 1 - accounts, sites, tenancy, and the platform trial lifecycle.

## Phase 1 - Accounts, sites, tenancy, and platform trial

Status: Complete. Sandbox billing credentials and both recurring prices are configured and verified; live activation remains environment-specific.

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
- Standard-plan cadence selection at $20 monthly or $220 yearly, using the confirmed Stripe price IDs and lookup keys
- Signed Stripe webhook validation, durable deduplicated event inbox, retryable failures, and audited state changes
- Scheduled subscription-access management command
- Initial migrations, admin screens, responsive templates, and production configuration checks

Verified locally:

- Ruff lint and format checks pass
- Django system and deployment checks pass
- No model/migration drift detected
- 23 automated tests pass
- Python dependency consistency check passes

Production activation still requires:

- Stripe API and webhook secrets
- A configured Stripe Billing Portal

Completed next milestone: Phase 2 - template site content, contacts, blog, recurring events, and the public calendar.

## Phase 2 - Template site, content, contacts, blog, and calendar

Status: Complete.

Completed:

- Classic and Social maintained presentation variants with validated color and typography tokens
- Site name, logo, hero image/copy, template, and public-publishing controls
- Fixed Home, About, Contact, and Newsletter pages with draft, published, and scheduled states
- Editable public navigation labels and escaped plain-text page content
- Blog post authoring, stable per-site slugs, draft/scheduled/published states, index, and detail pages
- JPEG, PNG, and WebP validation plus bounded image resizing before storage
- Tenant-scoped contacts with manual creation, editing, search, archive, tags, manager notes, and normalized per-site email uniqueness
- Auditable email/SMS consent state and low-friction public newsletter signup without overwriting manager-owned notes
- Single, weekly, and monthly events with materialized timezone-aware occurrences
- One-occurrence, selected-and-future, and entire-series edit scopes
- Public, unlisted, and invite-only visibility boundaries
- Public responsive home, calendar, event-series, and occurrence pages on subscriber subdomains
- Subscriber and manager dashboard links for website, contacts, and event operations

Verified locally:

- Configured Stripe sandbox prices are active USD recurring prices at $20 monthly and $220 yearly with the expected lookup keys
- Ruff lint and formatting checks pass
- Django system and production deployment checks pass
- No model/migration drift detected
- 37 automated tests pass
- Test settings cannot inherit Stripe secrets from `.env` or make accidental provider calls

Next: Phase 3 - invitations, RSVP responses, named guests, capacity, attendance, and core event reporting.
