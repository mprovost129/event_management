# Gather HQs Operations Runbook

## Release and rollback

1. Confirm a current database backup exists and record its identifier.
2. Build an immutable application image and run CI, including the dependency audit.
3. Run `python manage.py check --deploy --settings=config.Settings.prod` against the release configuration.
4. Apply migrations once with `python manage.py migrate --noinput`.
5. Start or replace web, Celery worker, and Celery beat processes from the same image.
6. Wait for `/health/live/` and `/health/ready/` to return HTTP 200.
7. Run `python manage.py launch_gate --json --fail-on-warning`.
8. Exercise one subscriber home page, event page, login, and platform-ops page.

For an application rollback, redeploy the previous immutable image only when its code is compatible with the applied schema. Do not reverse a data migration during an incident without a reviewed migration-specific plan. If integrity is uncertain, stop writes, preserve logs and backups, and restore into an isolated environment first.

## Monitoring and alerting

- Probe `/health/live/` every minute. It verifies the web process without depending on other services.
- Probe `/health/ready/` every minute. In production it verifies PostgreSQL, Redis, and recent worker/scheduler heartbeats.
- Run `python manage.py alert_summary --hours 1 --json --fail-on-alert` at least every five minutes from an external scheduler whose nonzero exit triggers the operator's alert channel.
- Run `python manage.py launch_gate --json` after every release and daily.
- Retain structured application logs by request ID and site ID. Never place secrets, raw webhook bodies, or unrestricted contact data in alerts.

Critical alerts include failed platform or Connect webhooks, failed communications callbacks, terminal outbox messages, and stale worker/scheduler heartbeats. Connected accounts needing attention are warnings and should be communicated to the subscriber.

## Provider-failure response

Stripe and communications use durable inbox/outbox records; provider redirects are never authoritative.

1. Check platform ops and `alert_summary` to identify the affected provider and time window.
2. Confirm the provider's status independently.
   For email, compare the Gather HQs outbox provider ID with the Resend email and webhook records; never replay an accepted send manually.
3. Keep queued records intact. Do not manually mark payments paid or messages delivered.
4. After recovery, run the appropriate bounded command:

```text
python manage.py sync_subscription_access
python manage.py reconcile_commerce --retry-failed-events
python manage.py dispatch_campaigns --limit 25
python manage.py deliver_outbound_messages --limit 100
python manage.py queue_event_reminders
python manage.py queue_review_requests --limit 500
```

5. Re-run `alert_summary`, reconcile affected money totals, and record the incident timeline.

## Backup and restore drill

The production database provider must take encrypted daily backups and retain enough history to recover an unnoticed issue. Enable point-in-time recovery when its cost is acceptable. Object-storage media needs versioning or an equivalent independent retention policy.

Quarterly, and before the pilot launch, perform this drill:

1. Create an isolated database and network boundary; never overwrite production for a drill.
2. Restore the selected backup and record backup time, restore start, and restore completion.
3. Point the same release image at the restored copy with all outbound email, SMS, and Stripe calls disabled.
4. Run `python manage.py post_restore_verify --confirm-restored-copy --json`.
5. Open one pilot site, event, roster, report, and data export; compare representative counts with the recorded production snapshot.
6. Record recovery point, recovery time, verification result, and cleanup owner.
7. Destroy the isolated copy through the hosting provider after evidence is retained.

## Incident priorities

- P1: cross-tenant exposure, suspected credential/payment compromise, corrupted registrations, or platform-wide unavailability. Stop affected traffic, preserve evidence, rotate exposed credentials, and notify impacted parties through the approved incident process.
- P2: payment reconciliation failure, sustained worker outage, provider delivery failure, or one subscriber unable to operate a live event. Stabilize within the event window and use only documented recovery commands.
- P3: isolated content, reporting, or cosmetic problem with a workaround. Track for normal release.

The launch owner must publish a staffed support address, an escalation phone path for the pilot event, and the hosting/provider console owners before public launch.
