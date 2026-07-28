from celery import shared_task

from .services import queue_due_review_requests as queue_review_requests


@shared_task
def queue_due_review_requests(limit=500):
    return queue_review_requests(limit=limit)
