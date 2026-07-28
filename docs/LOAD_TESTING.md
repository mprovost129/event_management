# Launch Load Testing

The specification baseline is 100 concurrent registrations/check-ins, up to 1,000 attendees per event, 5,000 contacts per site, and a warm-cache public-page p95 below two seconds excluding third-party checkout.

Run the read-only deployed-site probe from a host outside the application network:

```text
python loadtests/run_public_load.py --base-url https://pilot.gatherhqs.com --concurrency 100 --requests 1000 --path / --path /events/ --path /health/live/
```

The command warms each path, emits JSON, and exits nonzero if p95 exceeds two seconds or errors exceed one percent. Do not run it against production during a live event without operator approval.

The public probe is not a substitute for contention tests. PostgreSQL CI exercises simultaneous capacity allocation and must show no oversell. Before launch, use a production-like environment with synthetic contacts to perform a 100-user RSVP/check-in drill, then verify:

- confirmed active participants never exceed capacity;
- one contact/occurrence registration and one active primary participant remain unique;
- roster search and check-in remain responsive at 1,000 participants;
- no cross-tenant records appear;
- worker and database saturation return to baseline after the run.

Save the JSON output, release identifier, dataset size, database tier, worker/web concurrency, and graphs with the launch evidence.
