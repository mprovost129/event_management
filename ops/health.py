from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from communications.models import OutboundMessage, ProviderCallbackEvent
from payments.models import ConnectedAccount, ConnectWebhookEvent
from subscriptions.models import StripeWebhookEvent

from .models import SystemHeartbeat


def operational_alerts(*, hours=24):
    since = timezone.now() - timedelta(hours=hours)
    alerts = []

    def add(code, label, count, severity="critical"):
        if count:
            alerts.append(
                {"code": code, "label": label, "count": count, "severity": severity}
            )

    add(
        "platform_webhook_failed",
        "Failed platform-billing webhooks",
        StripeWebhookEvent.objects.filter(
            status=StripeWebhookEvent.Status.FAILED, received_at__gte=since
        ).count(),
    )
    add(
        "connect_webhook_failed",
        "Failed connected-account webhooks",
        ConnectWebhookEvent.objects.filter(
            status=ConnectWebhookEvent.Status.FAILED, received_at__gte=since
        ).count(),
    )
    add(
        "provider_callback_failed",
        "Failed communication callbacks",
        ProviderCallbackEvent.objects.filter(
            status=ProviderCallbackEvent.Status.FAILED, received_at__gte=since
        ).count(),
    )
    add(
        "message_delivery_failed",
        "Messages at terminal retry limit",
        OutboundMessage.objects.filter(
            status=OutboundMessage.Status.FAILED,
            attempts__gte=5,
            updated_at__gte=since,
        ).count(),
    )
    add(
        "connected_account_attention",
        "Connected accounts requiring attention",
        ConnectedAccount.objects.filter(
            status__in=(
                ConnectedAccount.Status.RESTRICTED,
                ConnectedAccount.Status.DISCONNECTED,
            )
        ).count(),
        severity="warning",
    )
    add(
        "connected_account_sync_failures",
        "Connected accounts with recent synchronization failures",
        ConnectedAccount.objects.filter(sync_failure_count__gt=0).count(),
        severity="warning",
    )
    if settings.HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS:
        threshold = timezone.now() - timedelta(
            seconds=settings.BACKGROUND_HEARTBEAT_MAX_AGE_SECONDS
        )
        for key, label in (
            ("worker_execution", "Worker heartbeat is stale"),
            ("scheduler_dispatch_observed", "Scheduler heartbeat is stale"),
        ):
            healthy = SystemHeartbeat.objects.filter(
                key=key, observed_at__gte=threshold
            ).exists()
            if not healthy:
                add(f"{key}_stale", label, 1)
    return alerts
