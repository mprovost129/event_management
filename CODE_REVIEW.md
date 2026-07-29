# GatherHQs MVP Code Review

## Review performed

- Extracted and inspected the application source.
- Compiled every real Python source file successfully.
- Excluded macOS archive metadata (`__MACOSX` and `._*`) because those binary resource-fork files are not Python source.
- Reviewed URL routing, registration, campaign delivery, provider callbacks, payment services, settings, and existing tests.
- Attempted to run the full pytest suite.

## Concrete defect corrected

### Invitation/contact authorization gap

`events.registration.save_response()` confirmed that an invitation belonged to the requested occurrence, but did not independently confirm that it belonged to the contact being registered. The public view currently supplies `invitation.contact`, so the normal browser flow was protected indirectly; however, the service boundary remained unsafe for future API endpoints, management commands, background jobs, or refactors.

Correction:

- Require `invitation.contact_id == contact.id` for invitation-sourced registrations.
- Added `test_invitation_cannot_be_used_for_a_different_contact`.

## Syntax and structural findings

- All application Python files compile successfully.
- The ZIP contains macOS metadata that generates null-byte syntax errors if a tool scans the entire archive indiscriminately. Remove `__MACOSX`, `.DS_Store`, `._*`, `__pycache__`, and `.pyc` files before distributing source archives.
- The project is already strongly tested for an MVP, with coverage across registration, attendance, campaigns, callbacks, payments, onboarding, subscriptions, operations, middleware, and tenant behavior.

## Test execution limitation

The included dependency pins target versions that were not available from the package index in this review environment, beginning with `asgiref==3.11.1`. Consequently, pytest could not collect tests here because Django and Stripe could not be installed. This is an environment/package-availability limitation rather than evidence that the tests fail.

Run locally in the project's supported Python environment:

```bash
python -m pip install -r requirements-dev.txt
python manage.py check
python manage.py makemigrations --check --dry-run
pytest -q
ruff check .
ruff format --check .
```

## Recommendations

1. Add a CI workflow that runs compilation, Ruff, Django checks, migration drift, and pytest on every push and pull request.
2. Add an archive/build script that excludes operating-system metadata, caches, local logs, uploaded media, secrets, and development databases.
3. Keep authorization checks inside service functions even when views already constrain their inputs.
4. Add smoke tests for the five primary journeys: signup/onboarding, site publication, public RSVP, invite-only RSVP, and paid checkout/webhook completion.
5. Add explicit cross-tenant tests for every write-oriented service, particularly payments, campaigns, attendance, exports, and administrative actions.
6. Add provider-failure tests for malformed webhook timestamps, unknown callback types, duplicate callbacks, delayed callbacks, and out-of-order engagement events.
7. Avoid broad `except Exception` handlers unless they log context, preserve safe state, and either re-raise or return a deliberately documented degraded response.
