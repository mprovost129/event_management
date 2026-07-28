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

Completed next milestone: Phase 4 - Stripe Connect onboarding, paid tickets, inventory holds, orders, refunds, and member dues.

## Phase 4 - Stripe Connect ticketing and member dues

Status: Complete in sandbox-ready application code. Live country availability and live Connect credentials remain deployment decisions.

Completed:

- Stripe-hosted onboarding with explicit Standard-equivalent controller responsibilities: subscriber pays Stripe fees, Stripe collects requirements and handles negative-balance liability, full Stripe Dashboard access
- Connected-account readiness, requirements, refresh, restriction, and disconnection state
- Paid feature gates that leave free events available before Connect onboarding
- Occurrence ticket types with site currency, sales windows, inventory, and per-order limits
- Paid RSVP state that does not consume confirmed capacity or permit check-in before payment
- Thirty-minute transactional inventory holds with scheduled expiration and recovery command
- Immutable order and line-item snapshots in connected-account context
- Direct Stripe Checkout sessions with no platform application fee
- One individually identifiable ticket per named primary attendee or guest after verified payment
- Full and partial subscriber-admin refunds with append-only financial transitions
- Refund, payment failure, late/duplicate event, dispute, and disconnected-account handling
- Monthly and yearly site membership plans, distinct member identities, connected-account recurring Checkout, and provider-maintained membership status
- Ticket and membership receipt messages through the durable outbox
- Dedicated signed Connect webhook endpoint with connected-account context validation, durable idempotent inbox, retry support, and out-of-order-safe state transitions
- Reconciliation tooling for account readiness, pending Checkout Sessions, recurring subscriptions, failed webhook events, and Stripe-reported charge fees
- Ticket gross, recorded Stripe fees, refunds, estimated ticket net, member-dues revenue, and membership-state reporting

Verified locally:

- 63 automated tests pass
- One simultaneous-capacity test is selected automatically in authoritative PostgreSQL CI and skipped by the local SQLite feedback loop
- Direct ticket and membership Checkout tests assert connected-account context and absence of application-fee parameters
- Signature verification, account-context mismatch, duplicate/out-of-order events, failures, refunds, disputes, and disconnects are covered
- Ruff, Django system checks, migration drift, and production deployment checks pass

Production activation still requires:

- A live Stripe Connect platform with supported launch countries confirmed
- Separate sandbox/live event destinations configured for events on connected accounts
- `STRIPE_CONNECT_WEBHOOK_SECRET` supplied by the environment secret manager
- One successful end-to-end sandbox onboarding, ticket purchase/refund, and member renewal using real Stripe-hosted pages before live mode

Completed next milestone: Phase 5 - newsletters, SMS, campaign delivery, and provider analytics.

## Phase 5 - Newsletters, SMS, and delivery analytics

Status: Complete in provider-ready application code. Production email and SMS vendors remain deployment decisions; SMS stays disabled until one is selected.

Completed:

- Tenant-scoped newsletter and SMS drafts with edit, preview, scheduling, test-send, duplicate, and reporting flows
- Audience selection for all eligible contacts, members, non-members, tags, event invitees, and event-response states
- Blog posts as independent starting content for newsletters
- Channel-specific marketing consent enforcement during preview, audience expansion, and immediately before provider delivery
- Unique hashed unsubscribe capabilities that withdraw consent and suppress queued marketing immediately
- Background campaign expansion, bounded outbox delivery, stale-job recovery, exponential retries, and safe message-body redaction
- Django email delivery adapter with one-click unsubscribe headers and a fail-closed SMS provider boundary
- SMS segment estimates, explicit usage confirmation, monthly/purchased allowances, transactional reservations, hard limits, and append-only usage records
- Signed vendor-neutral callback ingestion with durable idempotency and out-of-order-safe sent, delivered, bounce, failure, open, click, and unsubscribe processing
- Subscriber campaign reports plus platform-admin visibility into campaigns, recipient failures, SMS allowances and history, callbacks, and unsubscribe capabilities

Verified locally:

- Marketing suppression, unsubscribe, delivery-time consent rechecks, audience scoping, SMS limits, metering, callback idempotency, callback ordering, large-send batching, blog seeding, and campaign duplication are covered
- 77 automated tests pass; the PostgreSQL-only simultaneous-capacity test is skipped by the local SQLite feedback loop
- Ruff, formatting, Django system checks, and migration drift checks pass
- The Phase 5 migration applies successfully to the local development database

Production activation still requires:

- A production Django email backend and verified sender/domain configuration
- A selected production SMS provider adapter and customer-facing segment allowance/credit policy
- Vendor-specific callback signature verification or a trusted translation into the normalized callback contract
- Email and SMS sandbox deliverability tests with real provider callbacks

Next: Phase 6 - reviews, reporting completion, and platform operations.
