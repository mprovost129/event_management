#!/usr/bin/env bash
set -euo pipefail

python manage.py check
python manage.py makemigrations --check --dry-run
ruff check .
ruff format --check .
pytest -q
pip-audit
