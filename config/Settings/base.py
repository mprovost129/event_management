from pathlib import Path

from dotenv import load_dotenv

from config.env import env, env_bool, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Local development can use a git-ignored .env file. Production injects the same
# contract through its secret/environment manager.
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")

PLATFORM_NAME = env("PLATFORM_NAME", "Gather HQs")
PLATFORM_LONG_NAME = env("PLATFORM_LONG_NAME", "Gather Headquarters")
PLATFORM_DOMAIN = env("PLATFORM_DOMAIN", "localhost")
PLATFORM_CONTROL_HOSTS = env_list(
    "PLATFORM_CONTROL_HOSTS", (PLATFORM_DOMAIN, f"www.{PLATFORM_DOMAIN}")
)
PLATFORM_DEFAULT_CURRENCY = env("PLATFORM_DEFAULT_CURRENCY", "usd").lower()
STRIPE_STANDARD_MONTHLY_PRICE_ID = env(
    "STRIPE_STANDARD_MONTHLY_PRICE_ID",
    "price_1TyGKX2dujKmWAFggUOrejZz",
    allow_blank=True,
)
STRIPE_STANDARD_YEARLY_PRICE_ID = env(
    "STRIPE_STANDARD_YEARLY_PRICE_ID",
    "price_1TyGKX2dujKmWAFgx9MQuP3R",
    allow_blank=True,
)
STRIPE_STANDARD_MONTHLY_LOOKUP_KEY = env(
    "STRIPE_STANDARD_MONTHLY_LOOKUP_KEY", "standard_monthly"
)
STRIPE_STANDARD_YEARLY_LOOKUP_KEY = env(
    "STRIPE_STANDARD_YEARLY_LOOKUP_KEY", "standard_yearly"
)
STANDARD_MONTHLY_AMOUNT_CENTS = env_int("STANDARD_MONTHLY_AMOUNT_CENTS", 2000)
STANDARD_YEARLY_AMOUNT_CENTS = env_int("STANDARD_YEARLY_AMOUNT_CENTS", 22000)
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", "", allow_blank=True)
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", "", allow_blank=True)
STRIPE_CONNECT_WEBHOOK_SECRET = env(
    "STRIPE_CONNECT_WEBHOOK_SECRET", "", allow_blank=True
)
STRIPE_BILLING_PORTAL_CONFIGURATION_ID = env(
    "STRIPE_BILLING_PORTAL_CONFIGURATION_ID", "", allow_blank=True
)
SUBSCRIPTION_TRIAL_DAYS = env_int("SUBSCRIPTION_TRIAL_DAYS", 14)
SUBSCRIPTION_GRACE_DAYS = env_int("SUBSCRIPTION_GRACE_DAYS", 7)
SUSPENDED_DATA_RETENTION_DAYS = env_int("SUSPENDED_DATA_RETENTION_DAYS", 90)
REVIEW_TOKEN_MAX_AGE_DAYS = env_int("REVIEW_TOKEN_MAX_AGE_DAYS", 365)
HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS = env_bool(
    "HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS", False
)
BACKGROUND_HEARTBEAT_MAX_AGE_SECONDS = env_int(
    "BACKGROUND_HEARTBEAT_MAX_AGE_SECONDS", 180
)
PUBLIC_WRITE_RATE_LIMIT_MAX = env_int("PUBLIC_WRITE_RATE_LIMIT_MAX", 30)
PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS = env_int(
    "PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS", 900
)
RATE_LIMIT_TRUSTED_PROXY_COUNT = env_int("RATE_LIMIT_TRUSTED_PROXY_COUNT", 0)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "axes",
    # Local
    "users.apps.UsersConfig",
    "core.apps.CoreConfig",
    "ops.apps.OpsConfig",
    "sites.apps.SitesConfig",
    "subscriptions.apps.SubscriptionsConfig",
    "content.apps.ContentConfig",
    "contacts.apps.ContactsConfig",
    "events.apps.EventsConfig",
    "communications.apps.CommunicationsConfig",
    "attendance.apps.AttendanceConfig",
    "payments.apps.PaymentsConfig",
    "reviews.apps.ReviewsConfig",
]

AUTH_USER_MODEL = "users.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "core.middleware.RequestContextMiddleware",
    "sites.middleware.SiteResolutionMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours
AXES_LOCKOUT_CALLABLE = None

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.platform",
                "content.context_processors.site_navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

CELERY_BROKER_URL = env(
    "CELERY_BROKER_URL", env("REDIS_URL", "redis://localhost:6379/1")
)
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "deliver-outbound-messages": {
        "task": "communications.tasks.deliver_queued_messages",
        "schedule": 60.0,
    },
    "queue-event-reminders": {
        "task": "communications.tasks.queue_due_event_reminders",
        "schedule": 3600.0,
    },
    "release-expired-inventory-holds": {
        "task": "payments.tasks.release_inventory_holds",
        "schedule": 60.0,
    },
    "reconcile-connected-accounts": {
        "task": "payments.tasks.reconcile_connected_accounts",
        "schedule": 21600.0,
    },
    "dispatch-due-campaigns": {
        "task": "communications.tasks.dispatch_due_campaigns",
        "schedule": 60.0,
    },
    "queue-review-requests": {
        "task": "reviews.tasks.queue_due_review_requests",
        "schedule": 3600.0,
    },
    "record-background-heartbeat": {
        "task": "ops.tasks.record_background_heartbeat",
        "schedule": 60.0,
    },
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
}

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "", allow_blank=True)
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "", allow_blank=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "webmaster@localhost")
SUPPORT_EMAIL = env("SUPPORT_EMAIL", "", allow_blank=True)
EMAIL_DELIVERY_BACKEND = env("EMAIL_DELIVERY_BACKEND", "django").lower()
SMS_DELIVERY_BACKEND = env("SMS_DELIVERY_BACKEND", "disabled").lower()
COMMUNICATIONS_WEBHOOK_SECRET = env(
    "COMMUNICATIONS_WEBHOOK_SECRET", "", allow_blank=True
)
SMS_MONTHLY_SEGMENT_LIMIT = env_int("SMS_MONTHLY_SEGMENT_LIMIT", 0)
CAMPAIGN_EXPANSION_BATCH_SIZE = env_int("CAMPAIGN_EXPANSION_BATCH_SIZE", 500)
CAMPAIGN_DELIVERY_BATCH_SIZE = env_int("CAMPAIGN_DELIVERY_BATCH_SIZE", 100)

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be true.")

LOG_FORMAT = env("LOG_FORMAT", "plain").lower()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "core.logging.RequestContextFilter",
        },
    },
    "formatters": {
        "plain": {
            "format": "{levelname} {asctime} {name} request_id={request_id} "
            "site_id={site_id} {message}",
            "style": "{",
        },
        "json": {
            "()": "core.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json" if LOG_FORMAT == "json" else "plain",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}

# Security defaults common to all environments. Production adds HTTPS settings.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
