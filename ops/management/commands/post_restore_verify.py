import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from ops.models import AuditEvent
from sites.models import Site
from subscriptions.models import PlatformSubscription
from users.models import User


class Command(BaseCommand):
    help = (
        "Verify integrity on a restored, non-production database copy without mutation."
    )

    def add_arguments(self, parser):
        parser.add_argument("--confirm-restored-copy", action="store_true")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_restored_copy"]:
            raise CommandError(
                "Pass --confirm-restored-copy only after selecting an isolated restored database."
            )
        errors = []
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if pending:
            errors.append(f"{len(pending)} unapplied migration(s)")
        site_ids = Site.objects.values_list("id", flat=True)
        missing_subscriptions = Site.objects.exclude(
            id__in=PlatformSubscription.objects.values_list("site_id", flat=True)
        ).count()
        if missing_subscriptions:
            errors.append(
                f"{missing_subscriptions} site(s) lack a platform subscription"
            )
        payload = {
            "ok": not errors,
            "errors": errors,
            "counts": {
                "sites": len(site_ids),
                "users": User.objects.count(),
                "audit_events": AuditEvent.objects.count(),
            },
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if errors:
            raise CommandError("Restored database integrity verification failed.")
