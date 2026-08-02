from django.conf import settings
from django.urls import reverse


def control_host(request):
    """The platform's own host, for building an absolute URL to a control-app
    route from anywhere - including a tenant subdomain's page, which must
    never assume it can resolve a bare "core:xyz" path against itself."""
    request_host = request.get_host().split(":", 1)[0].lower().rstrip(".")
    hosts = [item.lower().rstrip(".") for item in (getattr(settings, "PLATFORM_CONTROL_HOSTS", ()) or ())]
    if request_host and request_host in hosts:
        return request_host
    if hosts:
        return hosts[0]

    if request_host:
        return request_host
    return settings.PLATFORM_DOMAIN


def control_origin(request):
    host = control_host(request)
    request_authority = request.get_host().rstrip(".")
    request_host = request_authority.split(":", 1)[0].lower()
    scheme = "https" if request.is_secure() else "http"

    # If this request is already on a recognized control host, keep the full
    # authority (including dev port) to avoid redirecting local links to a
    # production domain/port.
    control_hosts = {
        item.lower().rstrip(".")
        for item in (getattr(settings, "PLATFORM_CONTROL_HOSTS", ()) or ())
    }
    if request_host in control_hosts:
        host = request_authority

    # Preserve local development ports when targeting localhost-like hosts.
    if host in {"localhost", "127.0.0.1"}:
        port = request.get_port()
        if (scheme == "http" and port != "80") or (scheme == "https" and port != "443"):
            host = f"{host}:{port}"

    return f"{scheme}://{host}"


def platform(request):
    origin = control_origin(request)
    return {
        "platform_name": settings.PLATFORM_NAME,
        "platform_long_name": settings.PLATFORM_LONG_NAME,
        "platform_domain": settings.PLATFORM_DOMAIN,
        "support_email": settings.SUPPORT_EMAIL,
        "platform_admin_url": f"{origin}{reverse('admin:index')}",
        "platform_ops_url": f"{origin}{reverse('ops:dashboard')}",
    }
