# Gather HQs Application Review

Review date: July 30, 2026

## Overall assessment

Gather HQs is substantially beyond a typical MVP. The installed core platform
has deliberate tenant boundaries, secure capability links, consent history,
transactional payment state, idempotent provider callbacks, audit trails,
retention safeguards, operational health checks, and a strong primary journey.
The visual system is cohesive and the subscriber dashboard organizes a broad
product without feeling like a generic admin panel.

The product architecture and core implementation are strong. It should still be
treated as prelaunch because external provider evidence, restore testing,
manual accessibility review, final legal approval, and the gaps below remain.

## Critical package issue

The ZIP contains `workspace` and `notifications` source directories, migrations,
and tests, but neither app is registered in `INSTALLED_APPS` or included in the
root URL configuration. Their templates and two shared helpers referenced by the
views are also absent. As shipped, pytest stops during collection for those two
apps. The contacts/CRM module is active; the later tasks, files, volunteers,
sponsors, forms, automations, AI drafting, insights, and in-app notifications
are dormant code rather than usable features.

This should be resolved as a dedicated integration phase: restore the missing
templates/helpers, register both apps, add navigation, run migrations, and make
their full test suite pass. Do not simply register the apps without completing
the missing UI and shared dependencies.

## Legal and commerce gaps

- The previous legal pages were short prelaunch placeholders. They have been
  replaced by a product-specific legal center, but final facts and approval are
  still required.
- Paid tickets lack the event-specific refund-policy field promised by the V1
  specification.
- Commercial campaign emails lack the initiating subscriber's required postal
  address.
- SMS is correctly disabled, but provider-level inbound STOP/HELP handling must
  exist before it is enabled.
- Youth events require an explicit adult-controlled registration and
  parent/guardian authorization design before they are promoted as a supported
  use case.

## Package completeness gaps

The README references `.env.example`, `PRODUCT_VISION.md`,
`DEVELOPMENT_ROADMAP.md`, `CHANGELOG.md`, `ARCHITECTURE.md`,
`CONTRIBUTING.md`, and `TESTING_CHECKLIST.md`, but those files are not present in
this ZIP. Restore them from the working project or update the README so a new
developer is not sent to missing documentation.

## Recommended order

1. Complete legal/business identity and counsel review.
2. Add event-specific refund disclosure and commercial-email sender address.
3. Restore and integrate the workspace and notification modules.
4. Restore the missing environment and planning documents.
5. Complete real Stripe and Resend sandbox journeys.
6. Run production-like load, manual accessibility, and isolated restore tests.
7. Launch one controlled pilot before enabling broad public signup.
