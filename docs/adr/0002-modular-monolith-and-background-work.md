# ADR 0002: Django modular monolith with queued background work

Status: Accepted  
Date: July 28, 2026

## Context

The platform includes websites, events, communications, payments, memberships, reviews, and reporting. These domains need clear ownership, but the launch scale and cost target do not justify separately deployed services.

Email, SMS, recurrence generation, reminders, webhook follow-up, image processing, cleanup, and reporting rollups cannot safely block web requests.

## Decision

Build one Django deployment divided into domain-focused Django apps. Domain state transitions use explicit service functions and database transactions. Critical cross-domain behavior must not be hidden in Django signals.

Use Redis for caching, short-lived locks, rate limits, and the background queue. Celery is the selected worker and scheduler. A durable database outbox retains transactional messages before Celery dispatch so a broker interruption cannot lose committed invitations or confirmations. Jobs must be idempotent, bounded, observable, and retry-safe.

The initial web interface uses Django templates and progressive enhancement rather than a separate SPA. Internal service boundaries should permit a future API without building the deferred public API now.

## Consequences

- One deployable application keeps development and operations affordable.
- Domain apps can later be extracted only if measured scaling or team constraints justify it.
- Worker and scheduler processes become production dependencies when the first queued feature ships.
- Service boundaries and idempotency standards require discipline even though the code runs in one process space.
