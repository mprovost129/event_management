import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from ops.models import SystemHeartbeat


def readiness_status(*, require_background=None):
    require_background = (
        settings.HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS
        if require_background is None
        else require_background
    )
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        checks["database"] = False

    cache_key = f"health:{uuid.uuid4()}"
    try:
        cache.set(cache_key, "ok", timeout=10)
        checks["redis"] = cache.get(cache_key) == "ok"
        cache.delete(cache_key)
    except Exception:
        checks["redis"] = False

    if require_background:
        recent_after = timezone.now() - timedelta(
            seconds=settings.BACKGROUND_HEARTBEAT_MAX_AGE_SECONDS
        )
        try:
            checks["worker"] = SystemHeartbeat.objects.filter(
                key="worker_execution", observed_at__gte=recent_after
            ).exists()
            checks["scheduler"] = SystemHeartbeat.objects.filter(
                key="scheduler_dispatch_observed", observed_at__gte=recent_after
            ).exists()
        except Exception:
            # A missing migration or database error is an unhealthy dependency,
            # not a reason for the readiness endpoint itself to return a 500.
            checks["worker"] = False
            checks["scheduler"] = False
    else:
        checks["worker"] = True
        checks["scheduler"] = True
    return {"ok": all(checks.values()), "checks": checks}
