from django.core.management.base import BaseCommand

from communications.services import deliver_message, queued_message_ids


class Command(BaseCommand):
    help = "Deliver queued transactional and campaign messages without a Celery worker."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        delivered = 0
        for message_id in queued_message_ids(limit=options["limit"]):
            deliver_message(message_id)
            delivered += 1
        self.stdout.write(self.style.SUCCESS(f"Processed {delivered} message(s)."))
