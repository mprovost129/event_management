import json
import logging
from datetime import UTC, datetime

from django.conf import settings

from .request_context import request_id_var, site_id_var


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        record.site_id = site_id_var.get()
        record.release = settings.RELEASE_VERSION
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_var.get()),
            "site_id": getattr(record, "site_id", site_id_var.get()),
            "release": getattr(record, "release", settings.RELEASE_VERSION),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)
