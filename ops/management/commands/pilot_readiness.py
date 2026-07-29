import json

from django.core.management.base import BaseCommand, CommandError

from sites.models import Site
from sites.readiness import pilot_readiness


class Command(BaseCommand):
    help = (
        "Check whether one pilot site has the minimum data needed to operate an event."
    )

    def add_arguments(self, parser):
        parser.add_argument("site_slug")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        site = Site.objects.filter(slug=options["site_slug"]).first()
        if site is None:
            raise CommandError("Pilot site not found.")
        readiness = pilot_readiness(site)
        checks = {check["key"]: check["complete"] for check in readiness["required"]}
        recommendations = {
            check["key"]: check["complete"] for check in readiness["recommended"]
        }
        payload = {
            "ok": readiness["ok"],
            "site": site.slug,
            "checks": checks,
            "recommendations": recommendations,
        }
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if not payload["ok"]:
            raise CommandError("Pilot site is not ready.")
