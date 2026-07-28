from django.core.management.base import BaseCommand

from events.messaging import queue_due_reminders


class Command(BaseCommand):
    help = "Queue reminders for registrations occurring about 24 hours from now."

    def handle(self, *args, **options):
        count = queue_due_reminders()
        self.stdout.write(self.style.SUCCESS(f"Queued {count} reminder(s)."))
