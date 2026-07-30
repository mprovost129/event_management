# ruff: noqa: F403, F405
from django.core.exceptions import ImproperlyConfigured

from config.env import env, env_bool, env_int, env_list

from .base import *

DEBUG = False
HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS = env_bool(
    "HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS", True
)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES["staticfiles"] = {
    "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
}

MEDIA_STORAGE_BACKEND = env("MEDIA_STORAGE_BACKEND", "s3").lower()
if MEDIA_STORAGE_BACKEND == "s3":
    INSTALLED_APPS += ["storages"]
    bucket_name = env("AWS_STORAGE_BUCKET_NAME")
    s3_options = {
        "bucket_name": bucket_name,
        "region_name": env("AWS_S3_REGION_NAME", "", allow_blank=True) or None,
        "endpoint_url": env("AWS_S3_ENDPOINT_URL", "", allow_blank=True) or None,
        "access_key": env("AWS_ACCESS_KEY_ID", "", allow_blank=True) or None,
        "secret_key": env("AWS_SECRET_ACCESS_KEY", "", allow_blank=True) or None,
        "default_acl": None,
        "file_overwrite": False,
        "querystring_auth": env_bool("AWS_QUERYSTRING_AUTH", True),
    }
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            key: value for key, value in s3_options.items() if value is not None
        },
    }
elif MEDIA_STORAGE_BACKEND != "filesystem":
    raise ImproperlyConfigured(
        "MEDIA_STORAGE_BACKEND must be either 's3' or 'filesystem'."
    )

DATABASES["default"]["CONN_MAX_AGE"] = env_int("DB_CONN_MAX_AGE", 60)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL", "redis://127.0.0.1:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_DOMAIN = env("SESSION_COOKIE_DOMAIN", f".{PLATFORM_DOMAIN}")
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN", SESSION_COOKIE_DOMAIN)

if env_bool("TRUST_X_FORWARDED_PROTO", True):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
