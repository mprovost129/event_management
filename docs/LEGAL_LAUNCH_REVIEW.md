# Gather HQs Legal Launch Review

Last updated: July 30, 2026

This is an implementation and business-readiness checklist, not legal advice.
The public templates are deliberately marked as drafts until the final business
facts and professional review are complete.

## Policy set now included

- Legal Center
- Terms of Service
- Privacy Notice
- Cookie Notice
- Payments, Cancellations & Refunds
- Acceptable Use Policy
- Data Retention & Deletion
- Security & Responsible Disclosure
- Review Guidelines

The text is tailored to the actual Gather HQs model:

- a 14-day no-card subscriber trial;
- monthly and yearly auto-renewing platform plans;
- independent subscriber groups operating events and memberships;
- public, unlisted, and invite-only events;
- contacts, invitations, RSVPs, guests, attendance, and reviews;
- subscriber-connected Stripe accounts;
- a 3% application fee deducted from paid event-ticket proceeds;
- membership dues without a Gather HQs application fee during the pilot;
- consent-aware email and optional SMS campaigns;
- files, forms, waivers, volunteers, sponsors, tasks, automations, and optional
  AI drafting when those modules are enabled; and
- a delayed, two-administrator site-deletion process.

## Decisions that must be finalized

- The legal or registered business name that operates Gather HQs.
- A public business mailing address. A properly registered P.O. box or
  commercial mailbox may be preferable to publishing a home address, subject to
  professional advice.
- The staffed support, privacy, and security email addresses.
- The effective date, Massachusetts governing-law wording, and venue.
- Whether the limitation-of-liability cap, indemnification, and dispute language
  is appropriate for the final entity, insurance, customers, and launch states.
- Tax responsibility and the platform's application-fee treatment.
- A current list of production subprocessors and required data-processing
  agreements.
- Cloudmersive's terms, privacy notice, security materials, data-processing
  terms, processing locations, retention claims, and incident commitments for
  organization-document malware scanning.

Production checks intentionally fail while `LEGAL_DRAFT=true` or
`LEGAL_POSTAL_ADDRESS` is blank.

## Product work still required before the affected feature launches

### Paid event refund disclosure

Partly resolved. `Site.default_refund_policy` and an optional
`TicketType.refund_policy` override now exist, resolved through
`TicketType.effective_refund_policy`. A ticket type cannot be created without a
policy from one source or the other, the policy appears on public event pages
and at checkout, and a paid event is not launch-ready until one is set.

Still outstanding: the policy is read live rather than snapshotted onto the
order, so amending it later changes the terms shown for past purchases, and it
does not yet appear in the payment receipt. Snapshot it on `Order` at
reservation and add it to the receipt before paid tickets go live.

### Commercial email postal address

Partly resolved. `Site.postal_address` is collected under website settings, the
organization name and address now appear above the unsubscribe link in every
marketing email footer, and `launch_campaign` refuses an email campaign while
the address is blank. SMS is deliberately unaffected.

Still outstanding: the sender identity is not verified. The address is accepted
as typed, so a subscriber can supply an invalid one. Decide whether verification
is required before the pilot or accepted as subscriber responsibility under the
terms of service.

### SMS opt-out operations

SMS correctly remains disabled by default. Before enabling it, select a
provider, implement and test provider-level inbound STOP/HELP and reasonable
opt-out handling, keep suppression immediate, and confirm that subscriber
identity and required disclosures appear in messages.

### Minors and youth events

V1 is adult-led and must not accept direct use by children under 13. If youth
events are offered, registration should be adult-controlled and the product
should provide a clear parent/guardian authorization pattern, limited fields,
and subscriber guidance. Counsel should review the exact flow before marketing
the platform for youth programs.

### Terms assent

The current product decision is to avoid a required Terms checkbox and expose
policies through the footer/legal center. Keep that decision unless intentionally
changed, but have counsel evaluate whether the signup and paid-plan flow provide
the desired level of assent and notice.

## Review evidence to retain

- The approved policy files and effective date.
- The reviewer and business approver.
- Screenshots of signup, plan selection, cancellation, ticket checkout,
  membership checkout, campaign footer, and privacy request flow.
- A test data export and deletion workflow.
- Stripe, email, and—if enabled—SMS sandbox evidence.
- The current provider and subprocessor inventory.

## Authoritative reference points

- FTC CAN-SPAM compliance guide:
  https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- FTC COPPA rule and business guidance:
  https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa
- FCC unwanted call and text guidance:
  https://www.fcc.gov/consumers/guides/stop-unwanted-robocalls-and-texts
- Massachusetts information-security standards, 201 CMR 17.00:
  https://www.mass.gov/regulations/201-CMR-1700-standards-for-the-protection-of-personal-information-of-residents-of-the-commonwealth
- Massachusetts unfair and deceptive fee rules, 940 CMR 38.00:
  https://www.mass.gov/regulations/940-CMR-3800-unfair-and-deceptive-fees
- Stripe Connect charge responsibility:
  https://docs.stripe.com/connect/charges
- California privacy-rights overview, if and when applicable:
  https://oag.ca.gov/privacy/ccpa
