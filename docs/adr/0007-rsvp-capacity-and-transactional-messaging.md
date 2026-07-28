# ADR 0007: Lock occurrences for capacity and deliver messages through an outbox

Status: Accepted  
Date: July 28, 2026

## Context

An RSVP can reserve several occurrence spots because one response may include a primary attendee and named guests. Simultaneous responses must not oversell capacity. Invitations and confirmations must also survive provider or queue outages without making a browser request responsible for email delivery.

## Decision

Treat the materialized `EventOccurrence` as the concurrency boundary. The response service opens a database transaction, locks the occurrence row, excludes any current participants belonging to the response being changed, and verifies the requested participant count against capacity before replacing participant state.

Keep one current `Registration` per contact and occurrence. Going registrations have one active primary `Participant` plus one active participant for each named guest. Response changes cancel the previous participant snapshots and append a `RegistrationHistory` record rather than deleting history.

Invitation URLs use cryptographically random capability tokens. Only a SHA-256 digest is stored on the invitation. The raw capability is held temporarily in the durable outbound-message body for delivery and erased after the message is sent.

Transactional emails are first committed to `OutboundMessage`. After commit, Celery dispatches delivery through Redis. A periodic Celery task drains queued/failed messages, recovers stale processing state, and applies bounded retry delays. Per-site deduplication keys make confirmation and reminder creation idempotent. Management commands provide a recovery path when workers are unavailable.

## Consequences

- PostgreSQL serializes competing capacity changes for the same occurrence without globally locking other events.
- Maybe and not-going responses do not reserve capacity.
- Primary attendees and guests can be checked in independently because each has a stable participant row.
- Historical participant rows remain available for audits after RSVP changes.
- Production requires both Celery worker and beat processes in addition to the web process.
- Email message bodies are unavailable in the application after successful delivery; operational records retain recipients, type, status, attempts, timestamps, and provider-safe errors.
