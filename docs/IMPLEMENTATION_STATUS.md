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

Completed next milestone: Phase 3 - invitations, RSVP responses, named guests, capacity, attendance, and core event reporting.

## Phase 3 - Invitations, RSVP, guests, attendance, and reporting

Status: Complete.

Completed:

- Manager-selected email invitations for occurrence-specific contact lists
- Cryptographically random invitation capabilities stored only as SHA-256 hashes
- Invite-only event details and response forms available only through a valid, unexpired invitation URL
- Going, maybe, and not-going responses with one current registration per contact and occurrence
- Low-friction public/unlisted registration that creates or updates contacts without overwriting notes or consent
- Configurable per-event guest limits with required first and last names and optional guest email/phone
- Independent primary and guest participant records for going responses
- Immutable response-history records when a response or guest list changes
- Transactional occurrence locking and participant-based capacity enforcement
- Manager response overrides for contacts, including invite-only events
- Durable transactional email outbox for invitations, confirmations, event updates, cancellations, and reminders
- Celery 5.6 with Redis-backed workers and a periodic scheduler, plus management-command delivery fallbacks
- Idempotent message deduplication, bounded retries, stale-job recovery, and post-delivery body redaction
- Mobile-friendly searchable/filterable occurrence rosters with large check-in controls
- Independent participant and guest check-in, undo, append-only attendance history, and audit events
- Occurrence metrics for invitations, response states, participants, guests, remaining capacity, and attendance

Verified locally:

- 50 automated tests pass
- One simultaneous-capacity test is selected automatically in authoritative PostgreSQL CI and skipped by the local SQLite feedback loop
- Ruff lint and formatting checks pass
- Django system and migration-drift checks pass
- Test message delivery uses the in-memory email backend and cannot contact production providers

Operational requirements:

- Run one Celery worker and one Celery beat process against the configured Redis broker
- Keep the fallback message-delivery command available for recovery and operational diagnosis
- Monitor failed/stale outbox records and worker availability before real invitations are enabled

Next: Phase 4 - Stripe Connect onboarding, paid tickets, inventory holds, orders, refunds, and member dues.
