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

## Product placeholders

The product name, platform domain, default currency, and Stripe plan price remain environment values so development can continue before the commercial values are finalized:

- `PLATFORM_NAME`
- `PLATFORM_DOMAIN`
- `PLATFORM_DEFAULT_CURRENCY`
- `STRIPE_PLATFORM_PRICE_ID`

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

The production environment must provide a non-placeholder domain, allowed hosts, a durable media bucket, secure secrets, and the Stripe price ID before paid-plan activation is enabled.
