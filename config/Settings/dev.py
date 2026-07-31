# ruff: noqa: F401, F403
from config.settings.dev import *
# ruff: noqa: F403, F405
from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".localhost"]

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
INTERNAL_IPS = ["127.0.0.1"]

# Fast local iteration only. Test settings use the same override explicitly.
AUTH_PASSWORD_VALIDATORS = []
