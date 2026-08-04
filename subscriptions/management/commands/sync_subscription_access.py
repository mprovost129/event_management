from django.core.management.base import BaseCommand

from subscriptions.services import synchronize_pending_access


class Command(BaseCommand):
    help = "Synchronize expired trials and payment grace periods."

    def handle(self, *args, **options):
        result = synchronize_pending_access()
        self.stdout.write(
            self.style.SUCCESS(f"Updated {result['updated']} subscription(s).")
        )
