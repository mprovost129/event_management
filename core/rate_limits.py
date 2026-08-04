import hashlib
from functools import wraps

from django.conf import settings
from django.core.cache import cache

from .error_views import error_response


def client_address(request):
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
    material = f"{scope}:{site_key}:{client_address(request)}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"public-write-rate:{digest}"


def public_write_rate_limit(scope):
    """Limit unauthenticated/public POST volume without storing raw IP addresses."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method != "POST":
                return view_func(request, *args, **kwargs)
            resolved_scope = (
                scope(request, *args, **kwargs) if callable(scope) else scope
            )
            limit = settings.PUBLIC_WRITE_RATE_LIMIT_MAX
            window = settings.PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS
            key = _rate_limit_key(request, resolved_scope)
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
                response = error_response(
                    request,
                    status=429,
                    title="Too many attempts",
                    message="Please wait a bit and try again.",
                )
                response["Retry-After"] = str(window)
                return response
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
