# Changelog

All notable changes should be recorded here. Until the project adopts a formal release process, entries are grouped by development phase.

## Unreleased

### Added

- `DEVELOPMENT_ROADMAP.md`
- `PRODUCT_VISION.md`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `TESTING_CHECKLIST.md`
- `ROLE_MATRIX.md`
- Regression and tenant-isolation coverage for notifications and the Phase 1–7 workspace.
- Shared pagination for the principal tenant list views.
- Search and status filtering for the core tenant and operational directories.
- Composite indexes for common tenant/status/date workspace queries.
- Tenant-specific abuse-rate limiting for public form submissions.
- Cross-tenant object-ID regression coverage across the principal tenant applications.
- Automated baseline checks for data-table, responsive-region, and image accessibility markup.
- Immutable release identifiers in plain and JSON application logs.
- Fail-closed ClamAV streaming for organization-document uploads.
- Stripe subscription event-time tracking in migration `subscriptions/0004`.
- Later-phase workspace, communications, notifications, forms, AI, and audit records in subscriber data exports.

### Changed

- Project documentation now identifies production hardening and design-system refinement as the next recommended phase.
- Private organization documents now download through an authorized application endpoint.
- Document uploads enforce configurable extension and size limits; administrator-only documents remain restricted to subscriber administrators.
- Pytest discovery now includes the `notifications` and `workspace` apps.
- CI now selects PostgreSQL test settings instead of silently falling back to in-memory SQLite.
- Event and campaign list metrics now use bounded aggregate queries instead of per-record query loops.
- Volunteer-hour and sponsor-count list summaries now use database aggregates.
- Reporting and commerce status summaries now use bounded filtered aggregates.
- Destructive event, contact, review, document, and team actions request explicit confirmation.
- Destructive platform suspension, deletion, approval, and moderation actions request explicit confirmation.
- Responsive data tables expose scoped headers and named keyboard-scroll regions.
- Outbound-message and automation services reject cross-tenant related objects at the service boundary.
- Provider and background failures emit contextual logs while retaining durable failure records.
- Commerce ticket inventory summaries now use fixed-query aggregation.
- Delayed older Stripe subscription webhooks no longer regress newer billing state.

### Fixed

- Separate staff notifications without dedupe keys no longer collapse into one notification.
- Organization insight CSV export uses the implemented site display name and neutralizes spreadsheet formula prefixes.
- Phase 1–7 source now passes the configured Ruff lint and format gates.

## Phase 7 — Guided onboarding

### Added

- Quick Start workspace
- Launch-essential and optional setup checklists
- First-session test workflow
- Dashboard links to onboarding guidance

## Phase 6 — AI content assistant

### Added

- Saved AI content drafts
- Optional OpenAI Responses API integration
- Local structured-draft fallback
- Provider, model, generation status, and failure metadata

## Phase 5 — Organization insights

### Added

- Organization-wide operational reporting
- CRM, task, document, form, volunteer, sponsor, automation, and activity metrics
- CSV report export

## Phase 4 — Workflow automations

### Added

- Automation rules and execution history
- Form-submission trigger
- Create-task, add-tag, and record-activity actions
- Manual run workflow

## Phase 3 — Forms and waivers

### Added

- Configurable forms
- Public submission workflow
- Waiver agreement and typed electronic signature capture
- CRM matching and contact creation from submissions

## Phase 2 — Volunteers and sponsors

### Added

- Volunteer profiles, shifts, assignments, and service hours
- Sponsor profiles, sponsorships, commitments, invoices, and payment status

## Phase 1 — Organization workspace

### Added

- Expanded CRM contact profiles
- Organization and event tasks
- Organization document library
- Organization activity feed
- Workspace navigation additions

## Initial platform

### Added

- Authentication, organizations, websites, content, events, attendance, communications, payments, subscriptions, contacts, reviews, and platform operations
- In-app notifications and invite-response email notification workflow
- Authorized public-site link back to the management dashboard
- Consolidated background-processing heartbeat warning
