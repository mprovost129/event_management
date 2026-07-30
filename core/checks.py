from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


@register()
def product_configuration_check(app_configs, **kwargs):
    issues = []
    currency = settings.PLATFORM_DEFAULT_CURRENCY
    if len(currency) != 3 or not currency.isalpha():
        issues.append(
            Error(
                "PLATFORM_DEFAULT_CURRENCY must be a three-letter ISO currency code.",
                id="platform.E001",
            )
        )
    if settings.SUBSCRIPTION_TRIAL_DAYS <= 0:
        issues.append(
            Error(
                "SUBSCRIPTION_TRIAL_DAYS must be greater than zero.",
                id="platform.E002",
            )
        )
    if settings.SUBSCRIPTION_GRACE_DAYS < 0:
        issues.append(
            Error(
                "SUBSCRIPTION_GRACE_DAYS cannot be negative.",
                id="platform.E003",
            )
        )
    if settings.SUSPENDED_DATA_RETENTION_DAYS <= 0:
        issues.append(
            Error(
                "SUSPENDED_DATA_RETENTION_DAYS must be greater than zero.",
                id="platform.E015",
            )
        )
    if settings.REVIEW_TOKEN_MAX_AGE_DAYS <= 0:
        issues.append(
            Error(
                "REVIEW_TOKEN_MAX_AGE_DAYS must be greater than zero.",
                id="platform.E016",
            )
        )
    if settings.BACKGROUND_HEARTBEAT_MAX_AGE_SECONDS <= 0:
        issues.append(
            Error(
                "BACKGROUND_HEARTBEAT_MAX_AGE_SECONDS must be greater than zero.",
                id="platform.E017",
            )
        )
    if settings.PUBLIC_WRITE_RATE_LIMIT_MAX <= 0:
        issues.append(
            Error(
                "PUBLIC_WRITE_RATE_LIMIT_MAX must be greater than zero.",
                id="platform.E020",
            )
        )
    if settings.PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS <= 0:
        issues.append(
            Error(
                "PUBLIC_WRITE_RATE_LIMIT_WINDOW_SECONDS must be greater than zero.",
                id="platform.E021",
            )
        )
    if settings.RATE_LIMIT_TRUSTED_PROXY_COUNT < 0:
        issues.append(
            Error(
                "RATE_LIMIT_TRUSTED_PROXY_COUNT cannot be negative.",
                id="platform.E022",
            )
        )
    if settings.DOCUMENT_UPLOAD_MAX_BYTES <= 0:
        issues.append(
            Error(
                "DOCUMENT_UPLOAD_MAX_BYTES must be greater than zero.",
                id="platform.E029",
            )
        )
    allowed_document_extensions = settings.DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS
    if not allowed_document_extensions or any(
        not extension or not extension.isalnum()
        for extension in allowed_document_extensions
    ):
        issues.append(
            Error(
                "DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS must contain simple file extensions.",
                hint="Use comma-separated values such as pdf,docx,xlsx.",
                id="platform.E030",
            )
        )
    if settings.DOCUMENT_UPLOAD_SCAN_BACKEND not in {
        "disabled",
        "clamav",
        "cloudmersive",
    }:
        issues.append(
            Error(
                "DOCUMENT_UPLOAD_SCAN_BACKEND must be 'disabled', 'clamav', or "
                "'cloudmersive'.",
                id="platform.E031",
            )
        )
    if settings.CLAMAV_PORT <= 0 or settings.CLAMAV_TIMEOUT_SECONDS <= 0:
        issues.append(
            Error(
                "ClamAV port and timeout settings must be greater than zero.",
                id="platform.E032",
            )
        )
    if settings.CLOUDMERSIVE_TIMEOUT_SECONDS <= 0:
        issues.append(
            Error(
                "CLOUDMERSIVE_TIMEOUT_SECONDS must be greater than zero.",
                id="platform.E036",
            )
        )
    if settings.DOCUMENT_UPLOAD_SCAN_BACKEND == "cloudmersive":
        cloudmersive_url = urlparse(settings.CLOUDMERSIVE_API_URL)
        if cloudmersive_url.scheme != "https" or not cloudmersive_url.netloc:
            issues.append(
                Error(
                    "CLOUDMERSIVE_API_URL must be a valid HTTPS URL.",
                    id="platform.E037",
                )
            )
    if settings.EMAIL_DELIVERY_BACKEND not in {"django", "resend"}:
        issues.append(
            Error(
                "EMAIL_DELIVERY_BACKEND must be either 'django' or 'resend'.",
                id="platform.E025",
            )
        )
    if settings.PLATFORM_DOMAIN not in settings.PLATFORM_CONTROL_HOSTS:
        issues.append(
            Error(
                "PLATFORM_CONTROL_HOSTS must include PLATFORM_DOMAIN.",
                id="platform.E007",
            )
        )
    invalid_hosts = [
        host
        for host in settings.PLATFORM_CONTROL_HOSTS
        if "://" in host or "/" in host or ":" in host
    ]
    if invalid_hosts:
        issues.append(
            Error(
                "PLATFORM_CONTROL_HOSTS entries must be hostnames without schemes, paths, or ports.",
                id="platform.E008",
            )
        )
    return issues


@register(Tags.security, deploy=True)
def deployment_product_check(app_configs, **kwargs):
    if settings.DEBUG:
        return []

    issues = []
    if settings.PLATFORM_DOMAIN in {"localhost", "example.com", "example.test"}:
        issues.append(
            Warning(
                "PLATFORM_DOMAIN still uses a development or placeholder value.",
                id="platform.W001",
            )
        )
    if settings.RELEASE_VERSION in {"", "development", "unknown"}:
        issues.append(
            Warning(
                "Production logs need an immutable release identifier.",
                hint=(
                    "Set RELEASE_VERSION to the image or commit identifier; "
                    "Render uses RENDER_GIT_COMMIT automatically."
                ),
                id="platform.W004",
            )
        )
    configured_prices = (
        settings.STRIPE_STANDARD_MONTHLY_PRICE_ID,
        settings.STRIPE_STANDARD_YEARLY_PRICE_ID,
    )
    if not all(configured_prices):
        issues.append(
            Warning(
                "Both Standard monthly and yearly Stripe price IDs are required for paid plan activation.",
                id="platform.W002",
            )
        )
    else:
        if not settings.STRIPE_SECRET_KEY:
            issues.append(
                Error(
                    "STRIPE_SECRET_KEY is required when paid plan activation is enabled.",
                    id="platform.E005",
                )
            )
        if not settings.STRIPE_WEBHOOK_SECRET:
            issues.append(
                Error(
                    "STRIPE_WEBHOOK_SECRET is required when paid plan activation is enabled.",
                    id="platform.E006",
                )
            )
    if settings.STANDARD_MONTHLY_AMOUNT_CENTS <= 0:
        issues.append(
            Error(
                "STANDARD_MONTHLY_AMOUNT_CENTS must be greater than zero.",
                id="platform.E009",
            )
        )
    if settings.STANDARD_YEARLY_AMOUNT_CENTS <= 0:
        issues.append(
            Error(
                "STANDARD_YEARLY_AMOUNT_CENTS must be greater than zero.",
                id="platform.E010",
            )
        )
    if settings.STRIPE_SECRET_KEY and not settings.STRIPE_CONNECT_WEBHOOK_SECRET:
        issues.append(
            Error(
                "STRIPE_CONNECT_WEBHOOK_SECRET is required for connected-account commerce.",
                id="platform.E011",
            )
        )
    if (
        settings.STRIPE_CONNECT_WEBHOOK_SECRET
        and settings.STRIPE_CONNECT_WEBHOOK_SECRET == settings.STRIPE_WEBHOOK_SECRET
    ):
        issues.append(
            Error(
                "Platform and Connect webhook endpoints must use different signing secrets.",
                id="platform.E012",
            )
        )
    if getattr(settings, "MEDIA_STORAGE_BACKEND", "filesystem") == "filesystem":
        issues.append(
            Error(
                "Production media must use durable object storage.",
                hint="Set MEDIA_STORAGE_BACKEND=s3 and configure the S3-compatible bucket.",
                id="platform.E004",
            )
        )
    if settings.DOCUMENT_UPLOAD_SCAN_BACKEND == "disabled":
        issues.append(
            Error(
                "Production document uploads require malware scanning.",
                hint=(
                    "Set DOCUMENT_UPLOAD_SCAN_BACKEND=cloudmersive and configure "
                    "CLOUDMERSIVE_API_KEY, CLOUDMERSIVE_API_URL, and "
                    "CLOUDMERSIVE_TIMEOUT_SECONDS, or configure ClamAV."
                ),
                id="platform.E033",
            )
        )
    if (
        settings.DOCUMENT_UPLOAD_SCAN_BACKEND == "cloudmersive"
        and not settings.CLOUDMERSIVE_API_KEY
    ):
        issues.append(
            Error(
                "CLOUDMERSIVE_API_KEY is required for Cloudmersive scanning.",
                id="platform.E038",
            )
        )
    if settings.SMS_DELIVERY_BACKEND == "console":
        issues.append(
            Error(
                "The console SMS backend cannot be used in production.",
                id="platform.E013",
            )
        )
    if (
        settings.EMAIL_DELIVERY_BACKEND == "django"
        and settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend"
    ):
        issues.append(
            Error(
                "The console email backend cannot be used in production.",
                id="platform.E014",
            )
        )
    if settings.EMAIL_DELIVERY_BACKEND == "resend":
        if settings.EMAIL_BACKEND != "communications.email_backend.ResendEmailBackend":
            issues.append(
                Error(
                    "Django account email must use the Resend API backend when Resend delivery is enabled.",
                    hint=(
                        "Set EMAIL_BACKEND="
                        "communications.email_backend.ResendEmailBackend."
                    ),
                    id="platform.E028",
                )
            )
        if not settings.RESEND_API_KEY:
            issues.append(
                Error(
                    "RESEND_API_KEY is required when Resend email delivery is enabled.",
                    id="platform.E026",
                )
            )
        if not settings.RESEND_WEBHOOK_SECRET:
            issues.append(
                Error(
                    "RESEND_WEBHOOK_SECRET is required to verify Resend delivery events.",
                    id="platform.E027",
                )
            )
    elif not settings.COMMUNICATIONS_WEBHOOK_SECRET:
        issues.append(
            Warning(
                "Configure COMMUNICATIONS_WEBHOOK_SECRET to receive delivery analytics callbacks.",
                id="platform.W003",
            )
        )
    if not settings.SUPPORT_EMAIL:
        issues.append(
            Error(
                "SUPPORT_EMAIL is required for production account and policy support.",
                id="platform.E023",
            )
        )
    else:
        try:
            validate_email(settings.SUPPORT_EMAIL)
        except ValidationError:
            issues.append(
                Error(
                    "SUPPORT_EMAIL must be a valid email address.",
                    id="platform.E024",
                )
            )
    if not settings.HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS:
        issues.append(
            Error(
                "Production readiness must verify the Celery worker and scheduler.",
                hint="Set HEALTHCHECK_REQUIRE_BACKGROUND_WORKERS=true.",
                id="platform.E018",
            )
        )
    if "core.middleware.SecurityHeadersMiddleware" not in settings.MIDDLEWARE:
        issues.append(
            Error(
                "SecurityHeadersMiddleware is required in production.",
                id="platform.E019",
            )
        )
    expected_cookie_domain = settings.PLATFORM_DOMAIN.lstrip(".")
    if (settings.SESSION_COOKIE_DOMAIN or "").lstrip(".") != expected_cookie_domain:
        issues.append(
            Error(
                "The production session cookie must be shared with tenant subdomains.",
                hint=f"Set SESSION_COOKIE_DOMAIN=.{expected_cookie_domain}.",
                id="platform.E034",
            )
        )
    if (settings.CSRF_COOKIE_DOMAIN or "").lstrip(".") != expected_cookie_domain:
        issues.append(
            Error(
                "The production CSRF cookie must be shared with tenant subdomains.",
                hint=f"Set CSRF_COOKIE_DOMAIN=.{expected_cookie_domain}.",
                id="platform.E035",
            )
        )
    return issues
