# Gather HQs Development Roadmap

## Product direction

**Gather HQs is the digital headquarters for organizations.**

The platform should let an organization publish its website, manage people, run events, communicate, collect payments, coordinate work, retain records, and understand performance from one tenant-scoped workspace.

## Roadmap rules

- Keep the first-run experience simple: create account, create organization, configure brand, create first event, publish website.
- Do not expose advanced modules until they are useful to the customer.
- Every feature must enforce organization-level tenant isolation and role-based permissions.
- Prefer cohesive workflows over isolated feature pages.
- A phase is not complete until its tests, permissions, documentation, empty states, responsive behavior, and deployment requirements are addressed.
- Update this file and `CHANGELOG.md` whenever a phase changes status.

## Status legend

- `[x]` Completed in the repository
- `[~]` Implemented but requires production validation or refinement
- `[ ]` Planned
- `Deferred` Intentionally postponed

---

## Completed foundation

### Phase 0 — Core SaaS platform `[x]`

- Authentication and account management
- Organizations/sites and tenant-aware access
- Public marketing websites and content
- Events and calendars
- Open and invitation-only attendance flows
- Communications, campaigns, outbound messages, and provider callbacks
- Payments, memberships, refunds, connected accounts, and subscriptions
- Reviews
- Platform operations, audits, support, permissions, and health checks

### Phase 1 — Organization workspace `[~]`

- Expanded CRM/contact profiles
- Contact statistics, history, notes, tags, consent, membership, and event activity
- Organization and event tasks
- Organization documents and attachments
- Organization activity feed
- Workspace navigation and dashboard integration

**Validation still required:** full dependency-backed test suite, production file storage, permissions, pagination, search, bulk actions, and responsive review.

### Phase 2 — Volunteers and sponsors `[~]`

- Volunteer profiles, skills, availability, assignments, shifts, and hours
- Sponsor profiles, levels, commitments, invoices, payments, and event associations

**Validation still required:** operational workflows, reporting accuracy, permission coverage, and user acceptance testing.

### Phase 3 — Forms and waivers `[~]`

- Custom public forms
- Event, volunteer, application, registration, and general-purpose form types
- Electronic agreement and typed signature capture
- CRM matching and contact creation from submissions
- Submission activity logging

**Validation still required:** legal-language review, retention policy, export, anti-spam controls, accessibility, and signature audit review.

### Phase 4 — Workflow automations `[~]`

- Rule, trigger, action, and execution-history framework
- Form-submission trigger integration
- Create-task, add-tag, and record-activity actions
- Manual execution and failure logging

**Validation still required:** idempotency, retries, rate limits, background execution, additional triggers, additional actions, and admin safety controls.

### Phase 5 — Organization insights `[~]`

- Organization-wide operational dashboard
- CRM, task, document, form, waiver, volunteer, sponsor, activity, and automation metrics
- CSV export
- Links to existing event reporting

**Validation still required:** production-data reconciliation, time-zone behavior, large-tenant query performance, and export authorization.

### Phase 6 — AI content assistant `[~]`

- Saved AI content drafts
- Structured content types and source context
- Optional OpenAI integration
- Local fallback draft workflow
- Provider, model, status, and failure metadata

**Validation still required:** usage limits, billing/credits, audit requirements, prompt-injection handling, privacy controls, moderation, and cost observability.

### Phase 7 — Guided onboarding `[~]`

- Quick Start guide
- Launch-essential and optional workspace checklists
- Direct links to incomplete setup steps
- First-session end-to-end test path

**Validation still required:** new-account usability testing, analytics, progressive disclosure, and completion-state accuracy.

---

# Current priority: stabilization and commercial polish

## Phase 8 — Production hardening and design-system refinement `[ ]`

### Goal

Make the existing platform reliable, consistent, responsive, accessible, and ready for real organizations before adding another large module.

### Scope

- Run the complete Django test suite with pinned dependencies.
- Add regression tests for all phases added after the original MVP.
- Expand cross-tenant isolation and role-permission tests.
- Standardize page headers, cards, tables, forms, buttons, filters, badges, alerts, pagination, empty states, and confirmation dialogs.
- Add consistent search, sorting, filtering, pagination, and bulk actions where appropriate.
- Review all mobile and tablet layouts.
- Perform accessibility checks for keyboard navigation, labels, focus states, semantic structure, contrast, and screen-reader behavior.
- Profile slow database queries and add indexes/select-related/prefetch-related optimizations.
- Review background worker, scheduler, email, webhook, file-storage, and payment failure paths.
- Add structured logging, actionable error messages, and operational runbooks.
- Review destructive actions and implement confirmation and audit trails.
- Remove dead code, duplicate utilities, obsolete templates, and inconsistent naming.

### Completion checklist

- [ ] Full automated suite passes locally and in CI.
- [ ] Tenant-isolation suite passes for every organization-owned model.
- [x] Staff role matrix is documented and tested.
- [ ] Core workflows pass desktop and mobile user acceptance testing.
- [ ] Accessibility review has no critical issues.
- [x] Key list views support pagination and useful filtering.
- [ ] Background services and email delivery are verified in Render.
- [ ] File uploads use production-safe storage and access controls.
- [ ] Error monitoring and release logging are operational.
- [ ] Documentation reflects the deployed application.

**Priority:** Highest  
**Dependency:** None  
**Recommended release target:** v0.8 stabilization release

### Stabilization progress — July 2026

- Restored a passing Ruff lint/format gate for the Phase 1–7 additions.
- Corrected CI to run the suite against its PostgreSQL service, including the authoritative concurrency coverage.
- Added `notifications` and `workspace` to pytest discovery plus regression and cross-tenant coverage for their core workflows.
- Added application-authorized private document downloads, upload size/type validation, and subscriber-administrator-only document enforcement.
- Fixed notification creation without dedupe keys and organization-insight CSV export failures/formula injection risk.
- Added pagination to the principal tenant lists introduced before and during Phases 1–7.
- Added search/status filters across people, tasks, documents, events, campaigns, volunteers, sponsors, forms, automations, and AI drafts.
- Added tenant-specific rate limiting to public form submissions.
- Removed per-record event and campaign metric queries, replaced memory-heavy relationship prefetches with aggregates, and added composite workspace indexes in migration `0007`.
- Expanded cross-tenant detail-view coverage and added explicit confirmation to destructive event, contact, review, document, and team actions.
- Added cross-tenant identifier-substitution coverage for contact, content, event, campaign, payment, review, and attendance object endpoints, including destructive POST routes.
- Consolidated reporting and commerce status totals into bounded aggregate queries with a regression query ceiling.
- Added scoped data-table headers, named keyboard-scroll regions, labeled platform-operation controls, and confirmations for destructive platform actions, backed by static template checks.
- Added immutable release identifiers to plain and structured logs through `RELEASE_VERSION` or Render's `RENDER_GIT_COMMIT`.
- Enforced tenant consistency inside outbound-message and automation service boundaries and added safe contextual logging to durable provider/background failure paths.
- Expanded the subscriber data export to include communications, notifications, Phase 1–7 workspace data, form/waiver responses, AI drafts, and tenant audit history.
- Added fail-closed streamed ClamAV scanning for organization documents plus production deployment checks and scanner protocol tests.
- Added Stripe event-time ordering so delayed older subscription webhooks cannot regress newer billing state; migration `subscriptions/0004` stores the last applied provider event time.
- Replaced per-ticket inventory queries on the commerce dashboard with a fixed-query aggregate map.
- Documented the implemented staff role matrix in `ROLE_MATRIX.md`.

Phase 8 code-side stabilization is substantially complete. Production service validation, manual accessibility/mobile user acceptance testing, monitoring and alert routing, backup/restore testing, and deployment validation of private storage and the ClamAV service remain open.

---

## Phase 9 — Website Builder 2.0 `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Let each organization create a polished, useful website without code while preserving safe, structured content management.

### Recommended scope

- Reusable block-based page builder rather than unconstrained pixel-level drag-and-drop
- Navigation editor and page ordering
- Theme tokens for colors, type, spacing, buttons, and sections
- Hero, text, image, gallery, call-to-action, event list, calendar, form, sponsor, volunteer, newsletter, and contact blocks
- Page duplication, drafts, preview, publish scheduling, and revision history
- Per-page SEO title, description, social image, canonical settings, and index controls
- Reusable landing-page templates
- Custom domain readiness and domain verification workflow
- Accessibility safeguards and mobile previews

### Guardrails

- Sanitize all user-generated HTML.
- Keep public rendering fast and cacheable.
- Do not allow arbitrary scripts in standard plans.
- Maintain preview/published separation.

**Priority:** High  
**Dependencies:** Phase 8 design system, storage, permissions, and test coverage

---

## Phase 10 — Member portal `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Give members and invitees a secure self-service area that reduces administrative work and increases retention.

### Recommended scope

- Member login and profile management
- Household and dependent management
- Membership status, renewal, invoices, and receipts
- Event registrations, invitations, waitlists, tickets, and cancellations
- Signed waivers and required-document status
- Member-only announcements and documents
- Saved payment/customer portal integration where supported
- Communication preferences and consent management
- QR membership card and event tickets
- Secure account-claim flow for contacts already in the CRM

### Security requirements

- Explicit separation between public visitor, contact, member, staff, manager, and owner permissions
- Secure household/dependent authorization
- Rate limiting, session protection, and verified-email flows

**Priority:** High  
**Dependencies:** Phase 8, mature CRM identity matching, payments, documents, and forms

---

## Phase 11 — Financial center `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Provide a unified operational view of money moving through an organization without attempting to replace full accounting software initially.

### Recommended scope

- Invoices and payment requests
- Expense and reimbursement tracking
- Budgets by organization and event
- Sponsor and donation income
- Payout and fee reconciliation
- Refund and dispute visibility
- Financial categories and exports
- Receipt/document attachments
- Approval workflow for expenses and reimbursements
- Summary dashboards and board-ready reports

### Explicit boundary

Gather HQs should begin as an operational finance center, not a general-ledger accounting system. Integrations and exports should connect to accounting products rather than duplicating them prematurely.

**Priority:** High  
**Dependencies:** Phase 8, payments, documents, audit logging

---

## Phase 12 — Advanced automation builder `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Expand the existing rule engine into reliable multi-step workflows.

### Recommended scope

- Visual trigger → condition → action workflow editor
- Additional triggers: contact created/updated, RSVP, registration, payment, task overdue, membership renewal, document expiration, volunteer assignment, sponsor status, scheduled date
- Conditions, branching, delays, wait-until steps, and stop conditions
- Actions: send email, notify staff, create/update task, add/remove tag, update CRM field, request waiver, assign volunteer, generate AI draft, invoke webhook
- Versioning, dry runs, templates, retries, idempotency keys, rate limits, and execution replay
- Organization-level usage limits and observability

**Priority:** High  
**Dependencies:** stable worker/scheduler, Phase 8 observability, reliable communications and permission model

---

## Phase 13 — AI organization assistant `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Move beyond content drafting to contextual assistance while keeping humans in control.

### Recommended scope

- Generate newsletters, reminders, sponsor outreach, event descriptions, social copy, volunteer plans, and board summaries
- Summarize contact, event, form, report, and meeting data
- Suggest follow-up tasks and communication drafts
- Attendance and pricing suggestions clearly labeled as estimates
- Document summarization and date/obligation extraction
- Retrieval limited to authorized organization data
- Approval-first actions; AI must not publish, email, charge, refund, or modify critical records without explicit confirmation
- Usage metering, credits, cost limits, and model configuration
- Prompt and output audit records with sensitive-data controls

**Priority:** Medium-high  
**Dependencies:** Phase 8, mature AI governance, documents, reports, advanced automations

---

## Phase 14 — Mobile operations and PWA `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Support staff and volunteers during live events from phones and tablets.

### Recommended scope

- Installable progressive web app
- Event roster and check-in
- QR scanning
- Volunteer shift check-in/out
- Task completion and incident notes
- Contact lookup with permission-aware fields
- Push notifications
- Limited offline queue for check-ins with conflict reconciliation
- Mobile-first calendar and day-of-event dashboard

### Product decision gate

Build a native application only after PWA usage data proves that platform limitations materially harm core workflows.

**Priority:** Medium-high  
**Dependencies:** Phase 8 responsive design, member portal identity, notification infrastructure, event APIs

---

## Phase 15 — Public API, webhooks, and integrations `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Allow organizations and partners to connect Gather HQs to their existing systems safely.

### Recommended scope

- Versioned REST API
- Scoped API keys and OAuth where justified
- Webhook subscriptions, signing, retries, logs, and replay
- Import/export tools
- Initial integrations for calendar, accounting export, storage, SMS, and common productivity tools
- Developer documentation and sandbox/test mode

**Priority:** Medium  
**Dependencies:** Phase 8 security, stable domain models, audit logs, rate limiting

---

## Phase 16 — Marketplace and white-label expansion `[ ]` FUTURE - DO NOT UPDATE AT THIS TIME

### Goal

Create extensibility and higher-value plans after the core platform and API are stable.

### Recommended scope

- Theme and page-template marketplace
- Approved integration catalog
- Organization templates
- White-label branding controls
- Custom domains and email branding
- Enterprise SSO and provisioning
- Extension review, permission declarations, versioning, and revocation

**Priority:** Later  
**Dependencies:** Website Builder 2.0, API platform, mature billing and security

---

# Candidate future modules FUTURE - DO NOT UPDATE AT THIS TIME

These should be validated through customer interviews before implementation:

- Facility and room reservations
- Equipment checkout and inventory
- Board meetings, agendas, minutes, and voting
- Surveys and polls
- Fundraising campaigns, donations, auctions, and donor CRM
- Merchandise store
- Grant tracking
- Learning, certifications, and training records
- Badge and label printing
- Digital signage and kiosk mode
- SMS and push-notification packages

# Deliberately deferred

- Native mobile apps before the PWA proves insufficient
- Full accounting/general ledger
- Unrestricted free-form website scripting
- Marketplace before the API and permission model mature
- Autonomous AI actions involving money, publishing, permissions, or outbound communication
- Feature additions without a confirmed customer workflow or measurable business value

# Cross-cutting technical backlog

## Security

- Tenant isolation and object-level authorization
- Secure upload validation and malware-scanning strategy
- Rate limiting and abuse prevention
- Secrets and key rotation
- Dependency and container scanning
- Security headers and CSP
- Audit retention and privacy controls
- Backup and restore testing

## Reliability and operations

- CI/CD checks
- Error monitoring and alerting
- Worker and scheduler health
- Dead-letter/retry strategy
- Webhook observability
- Database backups and restore drills
- Storage lifecycle policies
- Data export and account deletion workflows

## Performance

- Query budgets for dashboard and reports
- Pagination on all unbounded lists
- Caching for public sites
- Image optimization
- Async processing for expensive exports and AI jobs
- Load testing for registrations and event-day check-ins

## Product analytics

- Onboarding funnel
- Time to first published site/event
- Module adoption
- Weekly active organizations
- Registration conversion
- Email delivery and engagement
- Retention and churn indicators
- Feature usage by subscription tier

# Release discipline

For every release:

- [ ] Update `CHANGELOG.md`.
- [ ] Update phase status in this roadmap.
- [ ] Run formatting, linting, checks, migrations, and tests.
- [ ] Review migration safety and rollback plan.
- [ ] Verify tenant isolation and permissions.
- [ ] Validate worker, scheduler, email, payments, uploads, and webhooks as applicable.
- [ ] Test core journeys on desktop and mobile.
- [ ] Confirm monitoring and backups.
- [ ] Document new environment variables and deployment steps.
