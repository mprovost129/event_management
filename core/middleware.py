import re
import uuid

from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.utils.deprecation import MiddlewareMixin

from .request_context import request_id_var, site_id_var

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class PlatformSessionMiddleware(SessionMiddleware):
    """Share login sessions across production subscriber subdomains."""

    def process_response(self, request, response):
        response = super().process_response(request, response)
        cookie = response.cookies.get(settings.SESSION_COOKIE_NAME)
        platform_domain = settings.PLATFORM_DOMAIN.lower().strip(".")
        host = request.get_host().split(":", 1)[0].lower().rstrip(".")
        if (
            cookie is not None
            and "." in platform_domain
            and (host == platform_domain or host.endswith(f".{platform_domain}"))
        ):
            cookie["domain"] = f".{platform_domain}"
        return response


class RequestContextMiddleware(MiddlewareMixin):
    """Provide bounded correlation data to logs and downstream responses."""

    def process_request(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request_id = (
            incoming if SAFE_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())
        )
        request.request_id = request_id
        request._request_context_tokens = (
            request_id_var.set(request_id),
            site_id_var.set("-"),
        )

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", str(uuid.uuid4()))
        response["X-Request-ID"] = request_id
        self._clear_context(request)
        return response

    def process_exception(self, request, exception):
        # Django still invokes process_response for handled exception responses.
        # Unhandled exceptions are cleared here to avoid leaking context.
        self._clear_context(request)
        return None

    @staticmethod
    def _clear_context(request):
        tokens = getattr(request, "_request_context_tokens", None)
        if not tokens:
            return
        request_id_token, site_id_token = tokens
        request_id_var.reset(request_id_token)
        site_id_var.reset(site_id_token)
        request._request_context_tokens = None


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Apply the application CSP and browser capability restrictions."""

    def process_response(self, request, response):
        response.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'",
        )
        response.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        return response
