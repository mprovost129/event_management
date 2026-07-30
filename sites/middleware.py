from django.conf import settings
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin

from core.request_context import set_site_id, site_id_var

from .models import SiteDomain


class SiteResolutionMiddleware(MiddlewareMixin):
    """Resolve verified subscriber hosts without trusting URL-provided tenant IDs."""

    def process_request(self, request):
        request.site = None
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
        platform_domain = settings.PLATFORM_DOMAIN.lower().rstrip(".")

        control_hosts = {
            *settings.PLATFORM_CONTROL_HOSTS,
            "localhost",
            "127.0.0.1",
            "testserver",
        }
        if host in control_hosts:
            return None

        domain = (
            SiteDomain.objects.select_related("site")
            .filter(hostname=host, is_verified=True)
            .first()
        )
        if domain is None:
            if host.endswith(f".{platform_domain}"):
                raise Http404("Site not found.")
            return None

        if request.path_info.startswith(
            ("/admin/", "/platform-admin/", "/platform-ops/")
        ):
            raise Http404("Page not found.")

        request.site = domain.site
        request._site_context_token = set_site_id(domain.site_id)
        return None

    def process_response(self, request, response):
        token = getattr(request, "_site_context_token", None)
        if token is not None:
            site_id_var.reset(token)
            request._site_context_token = None
        return response
