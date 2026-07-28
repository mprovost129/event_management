from celery import shared_task
from django.utils import timezone

from .models import SystemHeartbeat


@shared_task
def record_background_heartbeat():
    now = timezone.now()
    # Receipt of this beat-scheduled task proves that the scheduler dispatched
    # work and that a worker consumed it.
    for key in ("scheduler_dispatch_observed", "worker_execution"):
        SystemHeartbeat.objects.update_or_create(
            key=key,
            defaults={"observed_at": now, "details": {"task": "background_heartbeat"}},
        )
    return now.isoformat()
