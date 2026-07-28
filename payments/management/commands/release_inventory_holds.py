from django.core.management.base import BaseCommand

from payments.services import release_expired_holds


class Command(BaseCommand):
    help = "Release expired ticket inventory holds and expire their pending orders."

    def handle(self, *args, **options):
        count = release_expired_holds()
        self.stdout.write(self.style.SUCCESS(f"Released {count} expired hold(s)."))
