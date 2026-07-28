from django.core.management.base import BaseCommand

from subscriptions.models import PlatformSubscription
from subscriptions.services import synchronize_access


class Command(BaseCommand):
    help = "Synchronize expired trials and payment grace periods."

    def handle(self, *args, **options):
        count = 0
        ids = PlatformSubscription.objects.filter(
            status__in=(
                PlatformSubscription.Status.TRIALING,
                PlatformSubscription.Status.GRACE,
            )
        ).values_list("id", flat=True)
        for subscription_id in ids.iterator():
            before = PlatformSubscription.objects.values_list("status", flat=True).get(
                pk=subscription_id
            )
            after = synchronize_access(subscription_id)
            count += before != after.status
        self.stdout.write(self.style.SUCCESS(f"Updated {count} subscription(s)."))
