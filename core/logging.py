import json
import logging
from datetime import UTC, datetime

from django.conf import settings

from .context_processors import control_origin
from .request_context import request_id_var, site_id_var


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        record.site_id = site_id_var.get()
        record.release = settings.RELEASE_VERSION
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        request = getattr(record, "request", None)
        request_host = "-"
        request_host_name = "-"
        request_path = "-"
        request_method = "-"
        request_scheme = "-"
        request_route = "-"
        actor_user_id = None
        actor_is_superuser = None
        client_ip = "-"
        forwarded_for = "-"
        platform_route_on_non_control_host = False
        platform_control_origin = "-"
        if request is not None:
            request_path = getattr(request, "path", "-")
            request_method = getattr(request, "method", "-")
            request_scheme = getattr(request, "scheme", "-")
            resolver_match = getattr(request, "resolver_match", None)
            request_route = getattr(resolver_match, "view_name", "-") or "-"
            user = getattr(request, "user", None)
            if getattr(user, "is_authenticated", False):
                actor_user_id = getattr(user, "pk", None)
                actor_is_superuser = bool(getattr(user, "is_superuser", False))

            client_ip = request.META.get("REMOTE_ADDR", "-")
            forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "-")
            try:
                request_host = request.get_host()
                request_host_name = request_host.split(":", 1)[0].lower().rstrip(".")
            except Exception:
                request_host = "-"
                request_host_name = "-"

            if request_path.startswith(("/platform-admin/", "/platform-ops/")):
                control_hosts = {
                    *(getattr(settings, "PLATFORM_CONTROL_HOSTS", ()) or ()),
                    "localhost",
                    "127.0.0.1",
                    "testserver",
                }
                normalized_control_hosts = {
                    item.lower().rstrip(".") for item in control_hosts
                }
                if request_host_name != "-":
                    platform_route_on_non_control_host = (
                        request_host_name not in normalized_control_hosts
                    )
            try:
                platform_control_origin = control_origin(request)
            except Exception:
                platform_control_origin = "-"

        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "site_id": getattr(record, "site_id", site_id_var.get()),
            "release": getattr(record, "release", settings.RELEASE_VERSION),
            "status_code": getattr(record, "status_code", None),
            "request_host": request_host,
            "request_path": request_path,
            "request_method": request_method,
            "request_scheme": request_scheme,
            "request_route": request_route,
            "actor_user_id": actor_user_id,
            "actor_is_superuser": actor_is_superuser,
            "client_ip": client_ip,
            "forwarded_for": forwarded_for,
            "platform_route_on_non_control_host": platform_route_on_non_control_host,
            "platform_control_origin": platform_control_origin,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)
