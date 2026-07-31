from django.conf import settings
from django.urls import reverse


def _control_host(request):
    hosts = list(getattr(settings, "PLATFORM_CONTROL_HOSTS", ()) or ())
    if hosts:
        return hosts[0]

    request_host = request.get_host().split(":", 1)[0].lower().rstrip(".")
    if request_host:
        return request_host
    return settings.PLATFORM_DOMAIN


def _control_origin(request):
    host = _control_host(request)
    scheme = "https" if request.is_secure() else "http"

    # Preserve local development ports when targeting localhost-like hosts.
    if host in {"localhost", "127.0.0.1"}:
        port = request.get_port()
        if (scheme == "http" and port != "80") or (scheme == "https" and port != "443"):
            host = f"{host}:{port}"

    return f"{scheme}://{host}"


def platform(request):
    control_origin = _control_origin(request)
    return {
        "platform_name": settings.PLATFORM_NAME,
        "platform_long_name": settings.PLATFORM_LONG_NAME,
        "platform_domain": settings.PLATFORM_DOMAIN,
        "support_email": settings.SUPPORT_EMAIL,
        "platform_admin_url": f"{control_origin}{reverse('admin:index')}",
        "platform_ops_url": f"{control_origin}{reverse('ops:dashboard')}",
    }
