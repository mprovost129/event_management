# ruff: noqa: F403, F405
from .base import *

DEBUG = True

# Keep local tenant hosts on a dev-safe domain even when a shared .env carries
# production host values.
PLATFORM_DOMAIN = env("DEV_PLATFORM_DOMAIN", "localhost").strip().lower().rstrip(".")
PLATFORM_CONTROL_HOSTS = env_list(
    "DEV_PLATFORM_CONTROL_HOSTS", (PLATFORM_DOMAIN, f"www.{PLATFORM_DOMAIN}")
)

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    ".localhost",
    PLATFORM_DOMAIN,
    f".{PLATFORM_DOMAIN}",
]

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
INTERNAL_IPS = ["127.0.0.1"]

# Fast local iteration only. Test settings use the same override explicitly.
AUTH_PASSWORD_VALIDATORS = []
