from django.core.management.base import BaseCommand

from reviews.services import queue_due_review_requests


class Command(BaseCommand):
    help = "Queue review requests for checked-in attendees after their event ends."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)

    def handle(self, *args, **options):
        count = queue_due_review_requests(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Queued {count} review request(s)."))
