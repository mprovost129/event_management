from django.conf import settings
from django.http import Http404, HttpResponseRedirect
from django.utils.deprecation import MiddlewareMixin

from core.request_context import set_site_id, site_id_var

from .models import SiteDomain


class SiteResolutionMiddleware(MiddlewareMixin):
    """Resolve verified subscriber hosts without trusting URL-provided tenant IDs."""

    def process_request(self, request):
        request.site = None
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
        platform_domain = settings.PLATFORM_DOMAIN.lower().rstrip(".")
        canonical_control_host = (
            getattr(settings, "PLATFORM_CANONICAL_HOST", "").lower().rstrip(".")
        )

        control_hosts = {
            *settings.PLATFORM_CONTROL_HOSTS,
            "localhost",
            "127.0.0.1",
            "testserver",
        }
        if host in control_hosts:
            # The session/CSRF cookies are host-only (not shared across tenant
            # subdomains, see platform.E034/E035), so every alias of the control
            # app (e.g. the "www." host) must funnel browser navigation onto one
            # canonical host or a login on one alias won't be visible on another.
            # Non-GET/HEAD requests (webhooks, API calls) are left alone so a
            # server-to-server integration configured against an alias host never
            # has its request silently redirected.
            if (
                canonical_control_host
                and canonical_control_host in control_hosts
                and host != canonical_control_host
                and host in settings.PLATFORM_CONTROL_HOSTS
                and request.method in ("GET", "HEAD")
            ):
                return self._redirect_to_canonical_host(request, canonical_control_host)
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

    @staticmethod
    def _redirect_to_canonical_host(request, canonical_host):
        original_host = request.get_host()
        target_host = canonical_host
        if ":" in original_host:
            target_host = f"{canonical_host}:{original_host.split(':', 1)[1]}"
        url = f"{request.scheme}://{target_host}{request.get_full_path()}"
        return HttpResponseRedirect(url)

    def process_response(self, request, response):
        token = getattr(request, "_site_context_token", None)
        if token is not None:
            site_id_var.reset(token)
            request._site_context_token = None
        return response
