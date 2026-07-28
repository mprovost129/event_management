# ADR 0004: Gather HQs brand and domain routing

Status: Accepted  
Date: July 28, 2026

## Context

The product domain `gatherhqs.com` has been purchased. The product can be written as Gather HQs or expanded as Gather Headquarters. Each subscriber needs a memorable platform subdomain, while the root and `www` hosts must remain available for marketing, authentication, onboarding, and account management.

## Decision

Use **Gather HQs** as the primary interface and product name. Use **Gather Headquarters** as its expanded form in explanatory or formal copy.

Use `gatherhqs.com` as the tenant-root domain:

- Platform/control hosts: `gatherhqs.com` and `www.gatherhqs.com`
- Subscriber hosts: `{site-slug}.gatherhqs.com`
- Future custom domains: explicit verified `SiteDomain` records

Do not use `www.gatherhqs.com` as the tenant root because that would produce awkward subscriber addresses such as `{site-slug}.www.gatherhqs.com`.

## Consequences

- Production requires wildcard DNS and TLS coverage for `*.gatherhqs.com` in addition to the root and `www` hosts.
- `www` remains a reserved site slug.
- Host resolution must distinguish configured control hosts from subscriber domains before treating an unknown subdomain as a missing site.
- Local development continues to use `{site-slug}.localhost` through environment-specific settings.
