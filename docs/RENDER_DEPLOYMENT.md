# Render Deployment

The repository includes a cost-staged Blueprint at `render.yaml`. It uses free
resources for prelaunch traffic and data while retaining the paid background
processes required for the complete Gather HQs feature set:

| Resource | Purpose | Blueprint plan |
| --- | --- | --- |
| `gather-hqs-web` | Django and Gunicorn | Free web service during prelaunch |
| `gather-hqs-worker` | Celery delivery and scheduled work | Starter background worker |
| `gather-hqs-scheduler` | Celery beat schedule | Starter background worker |
| `gather-hqs-key-value` | Redis-compatible cache and Celery broker | Free Key Value during prelaunch |
| `gather-hqs-db` | Tenant and operational data | Free PostgreSQL during prelaunch |

Only the worker and scheduler are paid in the initial configuration because
Render does not offer free background workers or cron jobs. They preserve
queued delivery, reminders, campaign scheduling, inventory release,
reconciliation, and review requests. Committing or pushing `render.yaml` does
not create resources; applying the Blueprint does. Review Render's current
price estimate before selecting **Deploy Blueprint**.

This is a prelaunch configuration, not the final subscriber configuration:

- The free web service sleeps after 15 minutes without inbound traffic and can
  take about a minute to wake. Upgrade it to Starter before promoting the site
  publicly or inviting the pilot group.
- The free PostgreSQL database is limited to 1 GB, has no managed backups, and
  expires after 30 days. Upgrade it before storing any real subscriber data and
  no later than day 25 of the free database's life.
- Free Key Value has no disk persistence and loses its contents on restarts and
  when upgraded. Gather HQs keeps outbound-message and campaign state in
  PostgreSQL and periodically recovers pending work, but the broker must still
  be upgraded before real invitations, scheduled campaigns, or paid events.

This staging uses the free tiers as long as they do not affect a real user's
data or experience. The first public promotion, pilot invitation, or real
subscriber signup is the upgrade trigger—not the first successful payment.

## Before applying the Blueprint

1. Confirm CI passes on the deployment commit and that the repository is
   available to the Render account.
2. Create the final Stripe platform webhook destination at
   `https://gatherhqs.com/billing/stripe/` and the Connect destination at
   `https://gatherhqs.com/commerce/stripe/connect/`. Keep their signing secrets
   separate.
3. Create the Resend webhook at
   `https://gatherhqs.com/communications/callbacks/resend/` and select the event
   types listed in `EMAIL_SANDBOX_JOURNEY.md`.
4. Provision a private S3-compatible media bucket. Enable object versioning if
   the provider supports it. Record its bucket, region or endpoint, and scoped
   credentials.
5. Decide whether this is a sandbox rehearsal or live launch. Never mix test
   Stripe prices, keys, webhook secrets, or Billing Portal configuration with
   live-mode values.

## Create the Blueprint instance

In Render, open **Blueprints**, choose **New Blueprint Instance**, connect this
repository, and select `render.yaml`. Review all five resources and the monthly
estimate before applying it.

Render prompts for the following `sync: false` values on the initial Blueprint
creation. Values are stored on the web service and securely referenced by the
worker where needed:

| Variable | Required value |
| --- | --- |
| `STRIPE_STANDARD_MONTHLY_PRICE_ID` | Standard $20/month price for the selected Stripe mode |
| `STRIPE_STANDARD_YEARLY_PRICE_ID` | Standard $220/year price for the selected Stripe mode |
| `STRIPE_SECRET_KEY` | Matching restricted or secret platform key |
| `STRIPE_WEBHOOK_SECRET` | Platform webhook signing secret |
| `STRIPE_CONNECT_WEBHOOK_SECRET` | Connect webhook signing secret |
| `STRIPE_BILLING_PORTAL_CONFIGURATION_ID` | Matching-mode Billing Portal configuration |
| `RESEND_API_KEY` | Production or sandbox-rehearsal Resend API key |
| `RESEND_WEBHOOK_SECRET` | Resend/Svix webhook signing secret |
| `AWS_STORAGE_BUCKET_NAME` | Private media bucket name |
| `AWS_S3_REGION_NAME` | Bucket region, or blank when the provider does not use one |
| `AWS_S3_ENDPOINT_URL` | Provider endpoint, or blank for AWS S3 |
| `AWS_ACCESS_KEY_ID` | Bucket-scoped credential |
| `AWS_SECRET_ACCESS_KEY` | Bucket-scoped secret |

The Blueprint also routes Django account verification and password-reset email
through the Resend HTTPS API backend. No SMTP host, port, username, or password
is required.

Do not paste `.env` wholesale into Render. It can contain local or sandbox
values that should not be promoted. If a new `sync: false` variable is added
after the Blueprint already exists, add it to the service manually; Render only
prompts for these values during initial Blueprint creation.

The paid worker runs migrations as its pre-deploy command because Render does
not provide pre-deploy commands on free web services. The web container startup
collects static files and starts Gunicorn on Render's assigned `PORT`. The
Blueprint waits for repository checks before automatic deploys and uses
`/health/live/` as Render's deploy health check.

## Upgrade before the pilot

Before inviting any real user:

1. Export and verify the database, then change `gather-hqs-db` from `free` to
   `basic-256mb`, add a 5 GB disk, and enable the reviewed backup policy.
2. Change `gather-hqs-key-value` from `free` to `starter` and set persistence to
   `journal-snapshot`. The upgrade clears the free instance, so perform it
   before live work is queued. Restart the worker and scheduler afterward.
3. Change `gather-hqs-web` from `free` to `starter` so customer-facing pages no
   longer sleep after inactivity.
4. Sync the Blueprint, confirm the new monthly estimate, and run every
   first-deploy verification below again.

Keep the worker and scheduler on Starter throughout. Combining them with the
web process or using artificial traffic to prevent free-service sleep would
make scheduled work less reliable and is not part of the supported plan.

## Domain and DNS

The Blueprint declares both `gatherhqs.com` and `*.gatherhqs.com`. Render also
adds `www.gatherhqs.com` for the root domain and manages TLS certificates.

After the service exists:

1. Open the web service's **Custom Domains** section and copy the exact DNS
   targets Render displays.
2. Point the root domain to Render as instructed by the dashboard.
3. Add the wildcard `*` CNAME plus the wildcard certificate-validation CNAMEs
   shown by Render. The root domain must also point to Render for wildcard
   routing to work.
4. Remove conflicting web-hosting `AAAA` records if Render instructs you to do
   so, then verify the root and wildcard domains in Render.
5. Do not remove Resend's DKIM, SPF, or sending-domain records. Mail records can
   coexist with the root and wildcard records used for the website.
6. Confirm TLS works for `gatherhqs.com`, `www.gatherhqs.com`, and an actual
   subscriber hostname such as `pilot.gatherhqs.com`.

Keep the `gather-hqs-web.onrender.com` hostname enabled through initial setup so
there is an emergency diagnostic route. It can be disabled after custom-domain
and rollback procedures are proven; if disabled, remove it from `ALLOWED_HOSTS`
and `CSRF_TRUSTED_ORIGINS` too.

## First-deploy verification

Use a Render Shell on the paid worker after all services report deployed. Free
web services do not include shell access, and the worker uses the same release,
database, application settings, and provider configuration:

```text
python manage.py check --deploy --settings=config.Settings.prod
python manage.py launch_gate --json --fail-on-warning
python manage.py alert_summary --hours 1 --json --fail-on-alert
python manage.py pilot_readiness PILOT_SITE_SLUG --json
```

Then verify:

- `/health/live/` returns HTTP 200.
- `/health/ready/` returns HTTP 200 after the worker and scheduler heartbeats
  have had time to run.
- One subscriber site resolves on its subdomain and no tenant data appears on a
  different subscriber hostname.
- Static assets load and a test image upload is stored in object storage rather
  than the service filesystem.
- Stripe and Resend show successful, signature-verified webhook deliveries.
- `stripe_sandbox_journey SITE_SLUG --json` and
  `email_sandbox_journey SITE_SLUG --json` pass before switching to live mode.
- External monitoring probes both health endpoints and alerts a staffed owner.

Complete every remaining item in `LAUNCH_CHECKLIST.md` before accepting public
payments. In particular, verify a Render database backup by restoring it into an
isolated database; the presence of a managed database is not itself restore
evidence.

## Updating or rolling back

Blueprint services deploy automatically only after linked CI checks pass.
Migrations run before the new web release receives traffic. For rollback,
redeploy the previous successful commit only if its code is compatible with the
already-applied schema. Follow `OPERATIONS_RUNBOOK.md` if data integrity or a
provider callback is in doubt.

When changing from Stripe sandbox to live mode, update the two price IDs, API
key, both webhook secrets, and Billing Portal configuration as one controlled
release. Re-run the launch gate and a low-value end-to-end purchase before
opening sales.
