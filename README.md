# Gather HQs

Gather HQs (Gather Headquarters) is a multi-tenant Django platform for informal groups and emerging brands to publish branded sites, schedule events, invite contacts, collect RSVPs and payments, and understand attendance.

The production domain is `gatherhqs.com`. Subscriber sites use `{site-slug}.gatherhqs.com`; `gatherhqs.com` and `www.gatherhqs.com` are reserved for the platform itself.

The first customer is a country line dancing group. The product is intentionally designed around approachable group language rather than assuming every subscriber runs a registered business.

## Current milestone

Phase 1 is complete:

- Verified account signup
- Subscriber-site onboarding
- Platform subdomains
- Subscriber-admin and site-manager authorization
- Fourteen-day no-card trials
- Platform billing and Stripe webhook boundary
- Subscriber and manager dashboards

See [implementation status](docs/IMPLEMENTATION_STATUS.md) for verification results and the next phase.

## Documentation

- [V1 product and technical specification](docs/Event_Management_Platform_V1_Specification.md)
- [Development and environment guide](docs/DEVELOPMENT.md)
- [Architecture decisions](docs/adr)

## Quick start

Copy `.env.example` to `.env`, replace its development secrets, then run:

```text
docker compose up --build
docker compose exec web python manage.py migrate
```

Open `http://localhost:8000`. See the development guide for quality and deployment checks.
