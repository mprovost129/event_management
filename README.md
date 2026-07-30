# Gather HQs

Gather HQs (Gather Headquarters) is a multi-tenant Django platform for informal groups and emerging brands to publish branded sites, schedule events, invite contacts, collect RSVPs and payments, and understand attendance.

The production domain is `gatherhqs.com`. Subscriber sites use `{site-slug}.gatherhqs.com`; `gatherhqs.com` and `www.gatherhqs.com` are reserved for the platform itself.

The Standard plan includes all V1 features and is offered at $20 monthly or $220 yearly after a fourteen-day no-card trial.

The first customer is a country line dancing group. The product is intentionally designed around approachable group language rather than assuming every subscriber runs a registered business.

## Current milestone

Phase 7 launch hardening is complete in provider-ready application code:

- Verified account signup
- Subscriber-site onboarding
- Platform subdomains
- Subscriber-admin and site-manager authorization
- Fourteen-day no-card trials
- Platform billing and Stripe webhook boundary
- Subscriber and manager dashboards
- Branded, publishable subscriber websites with fixed pages and two maintained presentation variants
- Blog authoring and public newsletter signup with consent history
- Tenant-scoped contact management, tags, notes, search, and archive
- Single and recurring events with one/future/all occurrence editing
- Public calendars and public/unlisted/invite-only event visibility
- Secure contact invitations and going/maybe/not-going responses
- Named guests with occurrence-level capacity enforcement
- Queued confirmations, updates, cancellations, and event reminders
- Mobile occurrence rosters with independent participant check-in and history
- Core invitation, response, participant, capacity, and attendance metrics
- Stripe-hosted connected-account onboarding and readiness controls
- Paid event tickets with expiring inventory holds and direct connected-account Checkout
- One ticket per named participant, payment receipts, refunds, disputes, and financial history
- Monthly/yearly membership plans and recurring member dues in connected-account context
- Dedicated signed Connect webhook inbox, reconciliation commands, and commerce reporting
- Newsletter and SMS campaign drafts, audience previews, scheduling, test sends, and duplication
- Consent-aware audiences for all contacts, members, non-members, tags, event invitees, and RSVP states
- Blog-post-to-newsletter seeding and individualized unsubscribe capabilities
- Background audience expansion, bounded delivery batches, retries, and post-delivery message redaction
- SMS usage estimates, explicit confirmation, monthly allowances, reservations, and immutable usage history
- Idempotent delivery callbacks and campaign sent/delivered/bounce/open/click/unsubscribe reporting
- Signed review capabilities restricted to checked-in attendees after an event ends
- Public rating aggregates, subscriber responses, reporting, and audited platform moderation
- Consolidated site metrics and event comparison across registrations, attendance, revenue, and ratings
- Audited subscriber-admin JSON exports and read-only, expiring platform support access
- Reasoned suspension plus two-admin, delayed, cancelable site-retention deletion workflows
- Native Resend email delivery with signed delivery webhooks and suppression handling
- Cost-staged Render Blueprint for Django, Celery worker/beat, PostgreSQL, and Key Value, with explicit pre-pilot upgrade gates

Resend is the selected production email provider. Sender-domain, webhook, and end-to-end delivery evidence remain launch tasks. SMS is disabled by default and fails closed until a provider adapter and allowance are configured.

See [implementation status](docs/IMPLEMENTATION_STATUS.md) for verification results and the next phase.

## Documentation

- [V1 product and technical specification](docs/Event_Management_Platform_V1_Specification.md)
- [Development and environment guide](docs/DEVELOPMENT.md)
- [Render deployment guide](docs/RENDER_DEPLOYMENT.md)
- [Architecture decisions](docs/adr)
- [Legal launch review](docs/LEGAL_LAUNCH_REVIEW.md)
- [Application review - July 30, 2026](docs/APPLICATION_REVIEW_2026-07-30.md)

## Quick start

Copy only **Section 1 - Local development** from `.env.example` into `.env`,
replace its development secrets, then run:

```text
docker compose up --build
docker compose exec web python manage.py migrate
```

Open `http://localhost:8000`. See the development guide for quality and deployment checks.

### Organization workspace integration status

The ZIP contains source, migrations, and tests for tasks, documents, activity,
volunteers, sponsors, forms and waivers, workflow automation, AI drafting,
insights, and in-app notifications. Those two app packages are not yet
registered or routed, and their templates and shared helpers are not present in
this package. Treat them as integration work in progress rather than deployed
features. See
[the July 30 application review](docs/APPLICATION_REVIEW_2026-07-30.md) before
enabling them.

The separate Contacts/CRM feature listed in the core milestone is installed and
active.

## Project planning documents

- `PRODUCT_VISION.md` — product positioning, customers, principles, boundaries, and success measures
- `DEVELOPMENT_ROADMAP.md` — completed phases, production-hardening priority, and recommended future phases
- `CHANGELOG.md` — phase and release history
- `ARCHITECTURE.md` — application boundaries, tenant model, background processing, and deployment topology
- `CONTRIBUTING.md` — coding, testing, migration, permission, and documentation standards
- `TESTING_CHECKLIST.md` — release validation checklist for core platform workflows
