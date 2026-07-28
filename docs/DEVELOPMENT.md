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
