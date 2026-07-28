from django.core.management.base import BaseCommand

from communications.tasks import dispatch_due_campaigns


class Command(BaseCommand):
    help = "Queue due email and SMS campaigns for audience expansion."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=25)

    def handle(self, *args, **options):
        count = dispatch_due_campaigns(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Queued {count} campaign(s)."))
