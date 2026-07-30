import hashlib
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def _client_address(request):
    remote_address = request.META.get("REMOTE_ADDR", "unknown")
    trusted_proxies = settings.RATE_LIMIT_TRUSTED_PROXY_COUNT
    if trusted_proxies <= 0:
        return remote_address
    forwarded = [
        item.strip()
        for item in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if item.strip()
    ]
    if len(forwarded) <= trusted_proxies:
        return remote_address
    return forwarded[-(trusted_proxies + 1)]


def _rate_limit_key(request, scope):
    site = getattr(request, "site", None)
    site_key = str(site.id) if site is not None else "control"
    material = f"{scope}:{site_key}:{_client_address(request)}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"public-write-rate:{digest}"


def public_write_rate_limit(scope):
    """Limit unauthenticated/public POST volume without storing raw IP addresses."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method != "POST":
                return view_func(request, *args, **kwargs)
            limit = settings.PUBLIC_WRITE_RATE_LIMIT_MAX
            window = settings.PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS
            key = _rate_limit_key(request, scope)
            try:
                if cache.add(key, 1, timeout=window):
                    count = 1
                else:
                    count = cache.incr(key)
            except Exception:
                # Availability wins if Redis is interrupted; readiness and
                # monitoring report the cache failure independently.
                return view_func(request, *args, **kwargs)
            if count > limit:
                response = HttpResponse(
                    "Too many attempts. Please wait and try again.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )
                response["Retry-After"] = str(window)
                return response
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
