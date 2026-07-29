# Recommended Updates Implemented

## Security and correctness

- Retained the invitation/contact ownership validation added during the initial review.
- Corrected provider callback ordering so an older callback cannot move a campaign recipient's `last_event_at` backward.
- Added a regression test for out-of-order provider callbacks.

## Continuous integration

Added `.github/workflows/ci.yml`. On pushes and pull requests it runs:

1. PostgreSQL and Redis service containers
2. Dependency installation
3. `python manage.py check`
4. `python manage.py makemigrations --check --dry-run`
5. `ruff check .`
6. `ruff format --check .`
7. `pytest -q`
8. `pip-audit`

## Local validation

Added `scripts/validate.sh` to run the same primary checks locally.

## Clean source exports

Added `scripts/export_source.py`, which creates a source ZIP while excluding:

- `.env` files and environment variants
- SQLite databases
- Git and editor metadata
- Python caches and compiled files
- test/lint caches
- logs
- uploaded media
- macOS `__MACOSX`, `.DS_Store`, and `._*` metadata
- virtual environments and `node_modules`

Example:

```bash
python scripts/export_source.py --output dist/gatherhqs-source.zip
```

## Validation performed in this review environment

- All application Python files compile successfully.
- The generated ZIP passed `unzip -t` integrity validation.
- Full Django and pytest execution still requires installing the project's pinned dependencies in its normal development or CI environment.
