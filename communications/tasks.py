from celery import shared_task
from django.utils import timezone

from .campaigns import expand_campaign
from .models import Campaign
from .services import deliver_message, queued_message_ids


@shared_task
def deliver_outbound_message(message_id):
    deliver_message(message_id)


@shared_task
def deliver_queued_messages(limit=100):
    for message_id in queued_message_ids(limit=limit):
        deliver_outbound_message.delay(str(message_id))


@shared_task
def queue_due_event_reminders():
    from events.messaging import queue_due_reminders

    return queue_due_reminders()


@shared_task
def expand_campaign_task(campaign_id):
    return str(expand_campaign(campaign_id).id)


@shared_task
def dispatch_due_campaigns(limit=25):
    campaign_ids = list(
        Campaign.objects.filter(
            status=Campaign.Status.SCHEDULED,
            scheduled_for__lte=timezone.now(),
        )
        .order_by("scheduled_for")
        .values_list("id", flat=True)[:limit]
    )
    for campaign_id in campaign_ids:
        expand_campaign_task.delay(str(campaign_id))
    return len(campaign_ids)
