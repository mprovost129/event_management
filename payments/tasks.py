import stripe
from celery import shared_task
from django.db.models import F

from .models import ConnectedAccount
from .services import refresh_connected_account, release_expired_holds


@shared_task
def release_inventory_holds():
    return release_expired_holds()


@shared_task
def reconcile_connected_accounts(limit=100):
    account_ids = list(
        ConnectedAccount.objects.exclude(status=ConnectedAccount.Status.DISCONNECTED)
        .order_by(F("last_sync_attempted_at").asc(nulls_first=True), "created_at")
        .values_list("id", flat=True)[:limit]
    )
    refreshed = 0
    failed = 0
    for account_id in account_ids:
        connected = ConnectedAccount.objects.select_related("site").get(pk=account_id)
        try:
            refresh_connected_account(connected)
        except stripe.StripeError:
            failed += 1
        else:
            refreshed += 1
    return {"refreshed": refreshed, "failed": failed}
