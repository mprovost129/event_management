# Gather HQs Architecture

## Overview

Gather HQs is a modular Django SaaS application. The organization/site is the primary tenant boundary. Public website, event, CRM, operational, communication, payment, reporting, and workspace records must remain scoped to that tenant.

## High-level topology

```text
Browser / Public Visitor / Staff User
                |
                v
        Django Web Application
          |       |       |
          |       |       +--> Object/File Storage
          |       +----------> PostgreSQL
          +------------------> Redis-compatible Key Value
                                    |
                       +------------+-------------+
                       |                          |
                  Celery Worker              Celery Beat
                       |
             Email / scheduled jobs /
             reminders / automations
```

## Major Django modules

- `users` — authentication, account-level behavior, and user-facing notifications
- `sites` — organization/site ownership, branding, public-site configuration, staff access, and tenant context
- `content` — website pages, blog/news content, and public content rendering
- `events` — event definitions, scheduling, visibility, invitations, and event administration
- `attendance` — RSVP, registration, roster, and attendance behavior
- `contacts` — CRM contacts, members, memberships, consent, tags, and engagement data
- `communications` — outbound messages, campaigns, providers, callbacks, delivery jobs, and email integration
- `payments` — tickets, memberships, connected accounts, transactions, refunds, and financial flows
- `reviews` — review collection and management
- `subscriptions` — platform subscription and plan behavior
- `operations` — platform health, launch, support, audits, and operational administration
- `workspace` — tasks, documents, activity, volunteers, sponsors, forms, waivers, automations, reporting, AI drafts, and onboarding

Module boundaries should be reviewed as the workspace grows. Shared domain logic belongs in explicit services rather than large views or template code.

## Tenant model

The tenant boundary is the organization/site.

Required rules:

- Every organization-owned model must have a direct or reliably traversable tenant relationship.
- Querysets must be filtered by the current organization before object lookup.
- Object IDs, UUIDs, URLs, form values, and client-side hiding never substitute for authorization.
- Background tasks must carry an organization identifier and re-authorize access when practical.
- File paths, downloads, exports, API responses, reports, and AI context must be tenant-scoped.
- Tests must attempt cross-tenant reads and writes for every sensitive model.

## Authorization model

The application should distinguish at least:

- Anonymous public visitor
- Authenticated user without site access
- Contact/member portal user
- Site staff/editor
- Site manager
- Site administrator/owner
- Platform operator

Permissions should be centralized through reusable policy/service functions. Template visibility is a user-experience aid, not a security boundary.

The implemented capability details and test expectations are documented in `ROLE_MATRIX.md`.

## Background processing

Recommended Render services:

- Web application
- PostgreSQL database
- Render Key Value/Redis-compatible broker
- Celery worker
- Celery Beat scheduler

The worker handles outbound delivery and asynchronous work. Beat schedules recurring tasks and health heartbeats. Tasks should be idempotent where retries are possible and should expose visible status or logs for operationally important actions.

## Communications

The communications subsystem should separate:

1. Message/campaign intent
2. Queueing and scheduling
3. Provider delivery
4. Provider callbacks/webhooks
5. Delivery state and audit records

Provider webhooks must be authenticated, replay-safe, and observable. Email consent and unsubscribe behavior must be enforced at send time.

## Payments

Payment actions require:

- Tenant-scoped ownership
- Server-side amount calculation
- Provider object verification
- Idempotency for creates/refunds
- Webhook signature validation
- Explicit status transitions and audit trails
- No reliance on browser-supplied price or ownership data

## Files and documents

Production uploads should use object storage rather than ephemeral application disks. Requirements include:

- Validated file type and size
- Private-by-default access
- Authorization on download
- Safe filenames and generated storage keys
- Fail-closed ClamAV streaming before organization documents reach storage
- Retention/deletion policy
- Tenant-aware storage prefixes

## AI integration

AI requests should pass through a service layer that enforces:

- Organization authorization
- Deliberate context selection
- Minimal sensitive data disclosure
- Usage and cost limits
- Prompt/output audit metadata
- Human approval for consequential actions
- Clear failure and provider status

## Reporting

Reports should use tenant-scoped service functions. Large exports should move to background jobs. Metrics need documented definitions, organization time-zone handling, and tests that reconcile totals against source records.

## Deployment configuration

Environment-specific settings live under `config/Settings/`. Secrets must remain in environment variables. New services, variables, migrations, and operational requirements must be documented in the README and changelog.
