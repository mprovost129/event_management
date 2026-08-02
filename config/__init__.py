import sys

from . import settings as settings_package
from .celery import app as celery_app

# Render may retain a manually configured value from deployments that used the
# old, capitalized package name. Linux imports are case-sensitive, so keep that
# value working while deployments move to ``config.settings``.
sys.modules.setdefault("config.settings", settings_package)

__all__ = ("celery_app",)
