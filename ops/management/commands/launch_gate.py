import json

from django.core.checks import ERROR, WARNING, run_checks
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from core.health import readiness_status
from ops.health import operational_alerts


class Command(BaseCommand):
    help = (
        "Evaluate automated production launch gates without changing application data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--fail-on-warning", action="store_true")

    def handle(self, *args, **options):
        check_messages = run_checks(include_deployment_checks=True)
        errors = [str(item) for item in check_messages if item.level >= ERROR]
        warnings = [
            str(item) for item in check_messages if WARNING <= item.level < ERROR
        ]
        executor = MigrationExecutor(connection)
        migration_plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if migration_plan:
            errors.append(f"{len(migration_plan)} unapplied migration(s)")
        readiness = readiness_status()
        if not readiness["ok"]:
            errors.append("Readiness checks are not healthy")
        alerts = operational_alerts()
        if alerts:
            warnings.extend(
                f"{item['code']}: {item['label']} ({item['count']})" for item in alerts
            )
        payload = {
            "ok": not errors and (not options["fail_on_warning"] or not warnings),
            "errors": errors,
            "warnings": warnings,
            "readiness": readiness,
            "alerts": alerts,
        }
        if options["json"]:
            self.stdout.write(json.dumps(payload, sort_keys=True))
        else:
            self.stdout.write(
                "Launch gate: PASS" if payload["ok"] else "Launch gate: FAIL"
            )
            for error in errors:
                self.stdout.write(self.style.ERROR(f"ERROR: {error}"))
            for warning in warnings:
                self.stdout.write(self.style.WARNING(f"WARNING: {warning}"))
        if not payload["ok"]:
            raise CommandError("Launch gate failed.")
