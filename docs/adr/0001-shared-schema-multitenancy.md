# ADR 0001: Shared-schema row-level multitenancy

Status: Accepted  
Date: July 28, 2026

## Context

V1 targets approximately 100 subscriber sites and one PostgreSQL deployment. Each subscription owns one site, and a global user can interact with multiple sites. Operating cost and development simplicity are primary constraints, while cross-site data isolation is non-negotiable.

## Decision

Use one PostgreSQL database and one shared schema. Every tenant-owned aggregate stores an immutable site foreign key, directly or through a site-owned parent.

Host-resolution middleware will resolve a normalized hostname through an explicit site-domain record. Site-aware query services/managers and authorization policies will apply tenant scope. Public identifiers do not replace authorization.

Every tenant-owned endpoint requires tests covering:

- Access within the user's site and role
- Access to the same identifier shape on another site
- Anonymous access
- Suspended-site behavior

## Consequences

- Initial hosting, migrations, backups, and reporting remain simple and inexpensive.
- Cross-tenant joins for platform operations remain possible.
- A missing site predicate can create a serious exposure, so scoping helpers and regression tests are mandatory.
- Schema-per-tenant and database-per-tenant isolation remain possible future migrations but are not designed into V1 abstractions.
