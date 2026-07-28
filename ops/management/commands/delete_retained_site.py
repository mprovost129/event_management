from django.core.management.base import BaseCommand, CommandError

from ops.models import SiteDeletionRequest
from ops.services import execute_site_deletion


class Command(BaseCommand):
    help = "Execute one separately approved site deletion after its retention period."

    def add_arguments(self, parser):
        parser.add_argument("request_id")
        parser.add_argument("--confirm-site", required=True)

    def handle(self, *args, **options):
        deletion = SiteDeletionRequest.objects.filter(pk=options["request_id"]).first()
        if deletion is None:
            raise CommandError("Deletion request not found.")
        if options["confirm_site"] != deletion.site_slug:
            raise CommandError(
                "--confirm-site must exactly match the recorded site slug."
            )
        try:
            execute_site_deletion(deletion=deletion)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Deleted retained site {deletion.site_slug}.")
        )
