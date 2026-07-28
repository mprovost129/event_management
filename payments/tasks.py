from celery import shared_task

from .services import release_expired_holds


@shared_task
def release_inventory_holds():
    return release_expired_holds()
