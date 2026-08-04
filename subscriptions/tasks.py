from celery import shared_task

from .services import synchronize_pending_access


@shared_task
def sync_subscription_access():
    return synchronize_pending_access()
