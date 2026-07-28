from celery import shared_task

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
