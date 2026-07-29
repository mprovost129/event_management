# Pilot Event Runbook

This runbook is for the first country line dancing group. It deliberately uses only normal subscriber screens—no database intervention.

## One week before

1. Subscriber signs up, verifies email, chooses monthly or yearly billing, and completes Stripe Connect onboarding.
2. Complete the home, About, and Contact pages; publish the site.
3. Enter contacts manually under Contacts. Record marketing permission only when it was actually given.
4. Create and publish the event, venue, capacity, guest allowance, and ticket type if paid.
5. Send invitations or verify the public RSVP link in a private browser.
6. Open **Pilot launch center** from the subscriber workspace. Complete every required item and as many rehearsal items as practical.
7. The platform operator runs `python manage.py pilot_readiness SITE_SLUG --json`; every required check must be true.

## Day before

1. Subscriber reviews Going, Maybe, Not going, guests, and paid status from the roster/report.
2. Send a reminder through the event flow and confirm one real delivery.
3. Open the mobile roster on the phone that will be used at the door; test search and a reversible check-in.
4. Export the site data and retain it securely.
5. Operator confirms health/readiness, alert summary, provider status, and the latest backup.

## At the event

1. Use roster search by first name, last name, or email.
2. Check in only active Going participants whose payment is not required or is paid.
3. Use “Add response” for a walk-in contact; do not edit records in the database.
4. If the network fails, keep a minimal paper attendance list and enter it through the roster after service returns.
5. Escalate payment discrepancies; never treat a browser success page as proof of payment.

## After the event

1. Confirm attendance and no-show totals in Reports.
2. Let the scheduled review-request task queue links for checked-in attendees after the event end time.
3. Reconcile commerce and review any delivery/webhook alerts.
4. Hold a short operator/subscriber debrief and record confusing screens, manual workarounds, incorrect totals, and support requests.

Pilot acceptance requires the group leader to complete this runbook without developer database changes.
