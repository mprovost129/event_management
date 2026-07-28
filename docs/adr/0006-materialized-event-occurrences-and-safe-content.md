# ADR 0006: Materialize event occurrences and constrain public content

Status: Accepted  
Date: July 28, 2026

## Context

Gather HQs needs a useful public website and calendar before invitations, ticketing, and attendance are introduced. Recurring-event behavior must remain predictable once registrations and payments become occurrence-specific. Subscriber content must also be customizable without allowing arbitrary HTML, CSS, or scripts.

## Decision

Keep Phase 2 in three tenant-owned modules:

- `content` owns fixed pages, blog posts, publishing state, and safe presentation media.
- `contacts` owns people, tags, manager notes, and consent history.
- `events` owns event-series metadata and materialized occurrences.

Every recurring event creates explicit timezone-aware occurrence rows. An occurrence edit applies to one occurrence, the selected and future occurrences, or every occurrence. Later RSVP, capacity, ticket, attendance, and review records will reference an occurrence rather than a recurrence rule.

Public calendars list only published public events. Unlisted events are available through their stable direct URL but do not appear on the calendar. Invite-only events are unavailable through public routes until Phase 3 introduces authenticated invitation access.

V1 page and blog bodies are escaped plain text. Theme customization is limited to maintained template variants, validated color tokens, approved typography choices, and validated images. JPEG, PNG, and WebP uploads are bounded and resized before being handed to the configured storage backend.

## Consequences

- Occurrence-specific capacity and payment work can be added without reinterpreting historical recurrence rules.
- Recurrence changes update explicit rows and can be audited by scope.
- Materialization is capped to prevent an accidental unbounded series.
- Rich-text authoring and arbitrary inline website-builder output require a later sanitization and content-component design.
- Image processing adds Pillow as a production dependency.
