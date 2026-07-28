from django.core.management.base import BaseCommand

from payments.services import reconcile_site_commerce, retry_failed_connect_events
from sites.models import Site


class Command(BaseCommand):
    help = "Reconcile Stripe Connect readiness and in-flight commerce state."

    def add_arguments(self, parser):
        parser.add_argument("--site", dest="site_slug")
        parser.add_argument("--retry-failed-events", action="store_true")

    def handle(self, *args, **options):
        sites = Site.objects.all()
        if options["site_slug"]:
            sites = sites.filter(slug=options["site_slug"])
        errors = []
        for site in sites:
            result = reconcile_site_commerce(site)
            errors.extend(result["errors"])
            self.stdout.write(
                f"{site.slug}: account={result['account']} orders={result['orders']} "
                f"memberships={result['member_subscriptions']}"
            )
        if options["retry_failed_events"]:
            retry = retry_failed_connect_events()
            errors.extend(retry["errors"])
            self.stdout.write(f"Retried {retry['retried']} failed webhook event(s).")
        for error in errors:
            self.stderr.write(error)
        if errors:
            raise SystemExit(1)
