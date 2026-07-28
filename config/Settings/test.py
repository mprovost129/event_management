# ruff: noqa: F403, F405
from config.env import env

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", ".localhost"]
PLATFORM_DOMAIN = "localhost"
PLATFORM_CONTROL_HOSTS = ("localhost", "www.localhost")
STRIPE_SECRET_KEY = ""
STRIPE_WEBHOOK_SECRET = ""
STRIPE_BILLING_PORTAL_CONFIGURATION_ID = ""

if env("TEST_DATABASE_ENGINE", "sqlite").lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
