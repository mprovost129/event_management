# Gather HQs Release Testing Checklist

Use this checklist for production candidates. Mark items not applicable and explain why in the release notes.

## Build and configuration

- [ ] Dependencies install from the pinned files.
- [ ] Django system check passes.
- [ ] Migration plan is reviewed.
- [ ] Migrations apply to a fresh database.
- [ ] Migrations apply to a copy of the current schema/data.
- [ ] Static files build and serve correctly.
- [ ] Required environment variables are documented.
- [ ] Debug mode is disabled in production.

## Authentication and accounts

- [ ] Sign up, verification, login, logout, and password reset work.
- [ ] Session and redirect behavior is safe.
- [ ] Deactivated users lose access.
- [ ] Account/profile changes validate correctly.

## Organization and tenant isolation

- [ ] Organization creation and selection work.
- [ ] Owner, administrator, manager, staff, member, and public permissions match policy.
- [ ] Cross-tenant list/detail/create/update/delete attempts are denied.
- [ ] Cross-tenant UUID/object-ID substitution is denied.
- [ ] Cross-tenant files, exports, reports, tasks, and background jobs are denied.
- [ ] Public-site management links appear only for authorized staff.

## Public website and content

- [ ] Public/unpublished visibility works.
- [ ] Navigation and pages render on desktop and mobile.
- [ ] Blog/news publishing works.
- [ ] Images and uploads load from production storage.
- [ ] SEO metadata and canonical behavior are correct.
- [ ] Forms embedded in public content remain tenant-scoped.

## Events and attendance

- [ ] Create, edit, publish, unpublish, archive, and cancel work.
- [ ] Open, private, and invitation-only flows work.
- [ ] RSVP/register/change-response flows work.
- [ ] Capacity, waitlist, guest count, and duplicate-response behavior work.
- [ ] Roster, check-in, attendance, and export totals reconcile.
- [ ] Time-zone and daylight-saving behavior are correct.
- [ ] Invite responses create intended in-app/email notifications.

## CRM, members, and people

- [ ] Contact create, edit, archive, search, tags, notes, and consent work.
- [ ] Duplicate/matching behavior is deterministic.
- [ ] Event, invitation, attendance, payment, communication, and form history is correct.
- [ ] Membership lifecycle and totals reconcile.
- [ ] Sensitive fields are restricted by role.

## Tasks

- [ ] Organization and event task creation works.
- [ ] Assignment, status, priority, due date, checklist, comments, and attachments work.
- [ ] Upcoming/overdue/completed filters are correct.
- [ ] Recurring behavior, if enabled, is idempotent.
- [ ] Unauthorized users cannot view or modify tasks.

## Documents and files

- [ ] Upload type and size validation work.
- [ ] Private files require authorization.
- [ ] Public/member/manager/admin visibility rules work.
- [ ] Event/contact/task associations remain tenant-scoped.
- [ ] Download, replacement, archive/delete, and missing-file behavior work.
- [ ] Storage URLs do not leak unauthorized files.

## Volunteers and sponsors

- [ ] Volunteer profiles, skills, availability, shifts, assignments, check-in/out, and hours work.
- [ ] Capacity, no-show, cancellation, and completed-hour totals reconcile.
- [ ] Sponsor profiles, levels, event associations, commitments, invoices, and payment status work.
- [ ] Permission boundaries and exports are correct.

## Forms and waivers

- [ ] Active/inactive and closing-date behavior work.
- [ ] All field types validate and preserve answers.
- [ ] Required fields and option validation work.
- [ ] CRM matching/contact creation works.
- [ ] Waiver agreement and typed signature are required when configured.
- [ ] Acceptance timestamp and audit metadata are recorded.
- [ ] Spam, rate-limit, CSRF, and repeated-submission behavior are tested.
- [ ] Responses and exports are restricted to authorized staff.

## Communications and notifications

- [ ] In-app notifications create, count, link, mark-read, and mark-all-read correctly.
- [ ] Email consent and unsubscribe rules are honored.
- [ ] Campaign scheduling and delivery work.
- [ ] Provider callbacks/webhooks authenticate and update status.
- [ ] Bounces, complaints, failures, retries, and duplicates are handled.
- [ ] Email links and branding use the correct organization/domain.

## Automations and background processing

- [ ] Redis/broker connectivity works.
- [ ] Celery worker reports ready.
- [ ] Beat scheduler runs and heartbeat clears operations warnings.
- [ ] Form trigger and every enabled action execute once.
- [ ] Retries do not create duplicate tasks/messages/activity.
- [ ] Paused rules do not run.
- [ ] Failure logs are visible and do not leak secrets.
- [ ] Manual run honors permissions.

## Payments and subscriptions

- [ ] Prices and ownership are calculated server-side.
- [ ] Checkout success, cancel, failure, and duplicate callbacks work.
- [ ] Webhook signatures and idempotency work.
- [ ] Refunds, disputes, fees, connected accounts, and payouts reconcile.
- [ ] Membership/ticket access updates only after verified payment state.
- [ ] Platform subscription upgrades, downgrades, cancellation, and billing portal work.

## Reports and exports

- [ ] Organization metrics reconcile with source records.
- [ ] Event reports reconcile with registrations, attendance, refunds, and reviews.
- [ ] Date ranges and organization time zones are correct.
- [ ] CSV files open correctly and prevent spreadsheet-formula injection.
- [ ] Large exports are bounded or processed asynchronously.

## AI assistant

- [ ] No-key fallback works.
- [ ] Provider success, timeout, rate limit, invalid response, and failure behavior work.
- [ ] Tenant context does not cross organizations.
- [ ] Sensitive data and prompts are handled according to policy.
- [ ] Usage/cost limits are enforced when enabled.
- [ ] AI output is clearly a draft and requires human review.

## Onboarding

- [ ] Completion state reflects actual records.
- [ ] Links lead to the correct organization and screen.
- [ ] Optional steps are clearly identified.
- [ ] A new user can complete the first-event test path without documentation.

## Accessibility and responsive behavior

- [ ] Keyboard-only navigation works.
- [ ] Focus is visible and logical.
- [ ] Inputs have labels and errors are announced clearly.
- [ ] Tables and dialogs are accessible.
- [ ] Color contrast meets the project standard.
- [ ] Core workflows work at common phone, tablet, and desktop widths.

## Performance and resilience

- [ ] Key dashboards and lists avoid N+1 queries.
- [ ] Lists are paginated.
- [ ] Public pages and images meet performance targets.
- [ ] Registration/check-in load tests meet expected event volume.
- [ ] Provider outages fail safely and recover.
- [ ] Database backup and restore have been tested.

## Release and operations

- [ ] `CHANGELOG.md` and roadmap are updated.
- [ ] Error monitoring and logs are checked after deployment.
- [ ] Web, database, key value, worker, and scheduler services are healthy.
- [ ] Email, payments, uploads, webhooks, and scheduled jobs are smoke-tested.
- [ ] Rollback steps are documented.
- [ ] Post-deployment verification is complete.
