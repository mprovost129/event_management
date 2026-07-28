import json

from django.core.management.base import BaseCommand, CommandError

from contacts.models import Contact
from events.models import Event
from sites.models import Site, SiteRole


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
        checks = {
            "subscriber_admin": SiteRole.objects.filter(
                site=site,
                role=SiteRole.Role.SUBSCRIBER_ADMIN,
                is_active=True,
            ).exists(),
            "site_published": site.is_published,
            "active_access": site.accepts_public_traffic,
            "contacts_entered": Contact.objects.for_site(site).exists(),
            "published_event": Event.objects.for_site(site)
            .filter(status=Event.Status.PUBLISHED)
            .exists(),
        }
        payload = {"ok": all(checks.values()), "site": site.slug, "checks": checks}
        self.stdout.write(json.dumps(payload, sort_keys=True))
        if not payload["ok"]:
            raise CommandError("Pilot site is not ready.")
