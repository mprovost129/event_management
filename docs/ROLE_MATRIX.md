# Gather HQs role and permission matrix

This document describes the roles implemented today. It does not introduce the future member portal or additional staff tiers.

| Capability | Public visitor | Authenticated user without a site role | Site manager | Subscriber administrator | Platform superuser |
| --- | --- | --- | --- | --- | --- |
| View a published public site and public events | Yes | Yes | Yes | Yes | Yes |
| Submit public RSVPs and active public forms | Yes | Yes | Yes | Yes | Yes |
| Open a site management dashboard | No | No | Yes | Yes | Only with a tenant role |
| Manage contacts, events, communications, and operational workspace records | No | No | Yes | Yes | Only with a tenant role |
| View organization insights | No | No | Yes | Yes | Only with a tenant role |
| View or download staff documents | No | No | Yes | Yes | Only with a tenant role |
| View, upload, or delete administrator-only documents | No | No | No | Yes | Only with a subscriber-administrator role |
| Add or manage site managers | No | No | No | Yes | No; platform operations are separate |
| Export the complete tenant data archive | No | No | No | Yes | Through audited platform operations only |
| Use owner recovery for a suspended site | No | No | No | Yes | Through platform operations |
| Use platform operations and time-limited support access | No | No | No | No | Yes |

## Enforcement rules

- `SiteRole` currently has two tenant staff roles: `site_manager` and `subscriber_admin`.
- Tenant management views authorize the requested site first, then look up every object through a site-scoped queryset.
- Template visibility is not an authorization boundary. Sensitive views, downloads, exports, and write actions enforce roles server-side.
- Platform-superuser status does not silently grant a tenant role. Platform support access remains explicit, read-only, reasoned, expiring, and audited.
- Contacts and members do not yet have self-service accounts. That capability remains in the deferred member-portal phase.

## Required regression coverage

Changes to permissions must test the authorized role, the lower role where applicable, an authenticated outsider, anonymous access, and cross-tenant object substitution.
