# Development and Environment Guide

## Local setup

1. Copy `.env.example` to `.env` and replace the development passwords and secret.
2. Start PostgreSQL, Redis, and the web application with `docker compose up --build`.
3. Apply migrations with `docker compose exec web python manage.py migrate`.
4. Create a platform administrator with `docker compose exec web python manage.py createsuperuser`.
5. Open `http://localhost:8000`.

The Docker development image installs `requirements-dev.txt`. The production image installs only `requirements.txt` and runs as an unprivileged user.

## Quality commands

Run these before opening a pull request:

```text
ruff check .
ruff format --check .
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

Use `ruff check . --fix` and `ruff format .` for automated formatting. Migration files must be generated deliberately and committed with their model changes.

## Settings

- `config.Settings.dev` is the local server configuration.
- `config.Settings.test` is deterministic test configuration.
- `config.Settings.prod` enables HTTPS controls, Redis caching, compressed static files, and durable object storage.
- Application code must never import a specific environment settings module.

`.env` files are local-only and excluded from Git and Docker build contexts. Production secrets must be injected by the hosting platform's secret manager.

Local tests use an isolated SQLite database by default for fast feedback. CI sets `TEST_DATABASE_ENGINE=postgresql` and remains the authoritative PostgreSQL integration gate.

## Product configuration

The confirmed production brand is Gather HQs, expanded as Gather Headquarters. The tenant root is `gatherhqs.com`, producing addresses such as `boot-scooters.gatherhqs.com`. The following remain environment values so local, CI, staging, and production hosts stay isolated:

- `PLATFORM_NAME`
- `PLATFORM_LONG_NAME`
- `PLATFORM_DOMAIN`
- `PLATFORM_CONTROL_HOSTS`
- `PLATFORM_DEFAULT_CURRENCY`
- `STRIPE_STANDARD_MONTHLY_PRICE_ID`
- `STRIPE_STANDARD_YEARLY_PRICE_ID`
- `STRIPE_STANDARD_MONTHLY_LOOKUP_KEY`
- `STRIPE_STANDARD_YEARLY_LOOKUP_KEY`
- `STANDARD_MONTHLY_AMOUNT_CENTS`
- `STANDARD_YEARLY_AMOUNT_CENTS`

The Standard plan is $20 monthly or $220 yearly. Platform billing also requires `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`; keep those secrets blank in local development when testing non-payment flows. Checkout fails closed with a useful message rather than attempting a provider call when its Stripe secret is unavailable.

## Phase 1 flows

- Account signup: `/accounts/signup/`
- Account dashboard: `/dashboard/`
- Subscriber onboarding: `/start/`
- Stripe platform webhook: `/billing/stripe/`
- Platform administration: `/platform-admin/`

Subscriber sites resolve at `{slug}.{PLATFORM_DOMAIN}`. Modern browsers resolve `*.localhost` locally, so a site created as `boot-scooters` is available at `http://boot-scooters.localhost:8000` during development.

Schedule the subscription access command at least hourly once trials are exposed outside development:

```text
python manage.py sync_subscription_access
```

Stripe webhooks remain authoritative for paid activation, payment failure, recovery, and cancellation. Browser checkout redirects never change subscription access directly.

Test settings deliberately blank all Stripe secrets even when a developer `.env` contains sandbox credentials. Tests that exercise the gateway supply mocked keys explicitly, preventing accidental provider calls.

## Phase 2 flows

From a subscriber or manager dashboard:

- Website pages, blog, and publishing: `/sites/{site-id}/content/`
- Contacts: `/sites/{site-id}/contacts/`
- Events and occurrences: `/sites/{site-id}/events/`

On a published subscriber subdomain:

- Home: `/`
- About and Contact: `/about/` and `/contact/` when those pages are published
- Blog and posts: `/blog/` and `/blog/{post-slug}/`
- Newsletter signup: `/newsletter/`
- Public calendar and occurrences: `/events/` and `/events/{event-slug}/{occurrence-id}/`

Content bodies remain escaped plain text in V1. Uploaded logos, hero images, and blog images must be JPEG, PNG, or WebP, are limited to 10 MB, and are resized before storage. Production media continues to use the configured S3-compatible backend.

## Phase 3 flows and workers

Occurrence management adds these staff flows:

- Invite contacts: `/sites/{site-id}/occurrences/{occurrence-id}/invite/`
- Add or update a response: `/sites/{site-id}/occurrences/{occurrence-id}/responses/new/`
- Mobile roster and check-in: `/sites/{site-id}/occurrences/{occurrence-id}/roster/`

Public and invitation responses use:

- Public/unlisted response: `/events/{event-slug}/{occurrence-id}/respond/`
- Invite-only response capability: `/invitations/{random-token}/`

Invitation tokens are stored only as hashes. The raw token exists temporarily in a queued message body so it can be delivered, and that body is erased after successful delivery.

Start the worker and scheduler alongside the web process:

```text
celery -A config worker --loglevel=INFO
celery -A config beat --loglevel=INFO
```

Docker Compose defines `worker` and `beat` services. The beat process drains the durable message outbox every minute and queues event reminders hourly. If the broker or worker is unavailable, committed outbox rows remain recoverable. Operational fallbacks are:

```text
python manage.py deliver_outbound_messages --limit 100
python manage.py queue_event_reminders
```

Capacity is measured in active participant rows, including named guests. The registration service locks the occurrence row before checking and changing capacity. The authoritative simultaneous-request assertion runs in PostgreSQL CI; SQLite remains the fast local feedback database.

## Phase 4 Stripe Connect commerce

The platform Stripe context and subscriber-commerce Stripe context use separate webhook endpoints and secrets:

- Platform subscriptions: `https://gatherhqs.com/billing/stripe/` with `STRIPE_WEBHOOK_SECRET`
- Events on connected accounts: `https://gatherhqs.com/commerce/stripe/connect/` with `STRIPE_CONNECT_WEBHOOK_SECRET`

In Stripe Workbench, create the second destination with **Connected accounts** selected. Subscribe it to only these handled event types:

```text
account.updated
account.application.deauthorized
checkout.session.completed
checkout.session.async_payment_succeeded
checkout.session.async_payment_failed
checkout.session.expired
payment_intent.succeeded
payment_intent.payment_failed
charge.succeeded
charge.dispute.created
charge.dispute.updated
charge.dispute.closed
refund.created
refund.updated
refund.failed
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
customer.subscription.paused
customer.subscription.resumed
invoice.paid
invoice.payment_failed
```

Sandbox and live destinations have different signing secrets. Never reuse `STRIPE_WEBHOOK_SECRET` for the Connect endpoint. Stripe CLI can forward connected-account test events locally with:

```text
stripe listen --forward-connect-to localhost:8000/commerce/stripe/connect/
```

Commerce management is at `/sites/{site-id}/commerce/`. Only subscriber admins can connect Stripe, create membership plans, or issue refunds; site managers can create ticket types and view commerce reporting. Public membership plans are at `/memberships/`. Paid RSVPs receive a short-lived checkout capability and reserve ticket inventory for 30 minutes only after Stripe Checkout begins.

Ticket and dues Checkout Sessions, Products, Prices, Customers, Subscriptions, charges, and refunds are created with the connected account context. The application deliberately omits all application-fee parameters. No browser return marks an order paid; only a verified connected-account webhook or reconciliation does so.

Celery beat releases expired holds every minute. Operational fallbacks and reconciliation are:

```text
python manage.py release_inventory_holds
python manage.py reconcile_commerce
python manage.py reconcile_commerce --site boot-scooters --retry-failed-events
```

Reconciliation refreshes account readiness, in-flight Checkout Sessions, recurring member subscriptions, and Stripe-reported charge fees when available. Financial totals are operational reports, not an accounting ledger.

## Phase 5 campaigns and delivery analytics

Subscriber admins and site managers manage newsletters and SMS announcements at:

```text
/sites/{site-id}/campaigns/
```

Campaigns can target all eligible contacts, members, non-members, a tag, event invitees, or a selected RSVP response. Preview and delivery both enforce the separate marketing consent state for the selected channel. Recipient expansion runs as a background task, and the durable outbox is drained in bounded batches. Beat dispatches due campaigns every minute. Recovery commands are:

```text
python manage.py dispatch_campaigns --limit 25
python manage.py deliver_outbound_messages --limit 100
```

Email delivery uses Django's configured `EMAIL_BACKEND` through the internal `django` delivery adapter. Configure a production email backend rather than the console backend before launch.

SMS fails closed by default. A deployment must provide a production SMS adapter, set `SMS_DELIVERY_BACKEND`, and assign a nonzero `SMS_MONTHLY_SEGMENT_LIMIT` or purchased segment credit before SMS campaigns can launch. Every SMS launch and test send requires explicit usage confirmation; segments are reserved before audience expansion and moved to immutable accepted/released usage records.

Provider callbacks are accepted at `/communications/callbacks/{provider}/`. The current vendor-neutral adapter expects a JSON body containing `event_id`, `message_id`, `event_type`, and optional `occurred_at`, with a lowercase hexadecimal HMAC-SHA256 signature in `X-Communications-Signature` using `COMMUNICATIONS_WEBHOOK_SECRET`. Supported normalized event types are `sent`, `delivered`, `bounced`, `failed`, `opened`, `clicked`, and `unsubscribed`. A selected production vendor should translate its signed payload into this contract or add a vendor-specific verified adapter.

Marketing unsubscribe links are random capabilities stored only as SHA-256 hashes. Unsubscribing updates consent and suppresses already queued marketing immediately. Successful and terminal deliveries erase message bodies and raw unsubscribe URLs from the outbox.

## Phase 6 reviews, reports, and platform operations

Review requests are queued hourly for participants who remain checked in after an occurrence ends and have an email address. The fallback is:

```text
python manage.py queue_review_requests --limit 500
```

Each message contains a signed, site-bound participant capability. Submission rechecks current check-in status and event end time. A participant can maintain one review, edit it through the same capability, or soft-delete its public content. Subscriber staff can respond or report a review at `/sites/{site-id}/reviews/`; reporting does not hide content. Only a platform superuser can hide or restore a review, and every moderation action requires a reason and creates both moderation history and an audit event.

Authoritative consolidated reports are available at `/sites/{site-id}/reports/`. Subscriber admins can download an audited JSON data export from the site dashboard; site managers cannot export. The export includes site content, contacts, memberships, events, registrations, participants, attendance history, commerce totals, and reviews without exporting Stripe secrets.

Platform superusers use `/platform-ops/` to locate sites/users, inspect subscription and connected-account state, review failed webhooks/callbacks/messages, moderate reported reviews, and open explicit support access. Support access is read-only, reasoned, expires in at most eight hours, and audits every snapshot view.

Site deletion is intentionally not a normal model delete. A site must first be suspended, canceled, or archived. One platform administrator requests deletion and a different administrator approves it, starting `SUSPENDED_DATA_RETENTION_DAYS`. The request can be canceled during retention. After eligibility, an operator must supply both the request UUID and exact recorded slug:

```text
python manage.py delete_retained_site REQUEST_UUID --confirm-site exact-site-slug
```

That command permanently deletes the site and its retained tenant records. Generate and secure the subscriber export before approval when policy requires it.

## Production media

Production uses an S3-compatible bucket through `django-storages`. Configure `MEDIA_STORAGE_BACKEND=s3`, the bucket, its region or endpoint, and credentials supplied by the hosting platform. Local filesystem media is intentionally rejected by the deployment system check.

Subscriber-provided HTML, CSS, and JavaScript must not be written directly into static files. Public template customization will use validated theme tokens and media records.

## Request tracing and auditing

Every response receives a bounded `X-Request-ID`. Application logs include that request ID and a site ID placeholder. Future host-resolution middleware will set the site context after it identifies the tenant.

Use `ops.services.record_audit_event` for privileged or sensitive domain actions such as role changes, refunds, moderation, exports, support access, and deletion requests. Summaries must contain identifiers and safe state descriptions, not credentials, payment payloads, message bodies, or unrestricted personal data.

## Deployment checks

Run Django's standard deployment checks with production settings and production-like environment variables before release:

```text
python manage.py check --deploy --settings=config.Settings.prod
```

The production environment must provide a non-placeholder domain, allowed hosts, a durable media bucket, secure secrets, and both Standard-plan Stripe price IDs before paid-plan activation is enabled.
