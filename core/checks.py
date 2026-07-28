from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


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
    if not settings.STRIPE_PLATFORM_PRICE_ID:
        issues.append(
            Warning(
                "STRIPE_PLATFORM_PRICE_ID is blank; paid plan activation is disabled.",
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
    if getattr(settings, "MEDIA_STORAGE_BACKEND", "filesystem") == "filesystem":
        issues.append(
            Error(
                "Production media must use durable object storage.",
                hint="Set MEDIA_STORAGE_BACKEND=s3 and configure the S3-compatible bucket.",
                id="platform.E004",
            )
        )
    return issues
