from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError

RESERVED_SITE_SLUGS = {
    "accounts",
    "admin",
    "api",
    "app",
    "billing",
    "dashboard",
    "help",
    "mail",
    "media",
    "static",
    "status",
    "support",
    "www",
}


def validate_site_slug(value):
    if value.lower() in RESERVED_SITE_SLUGS:
        raise ValidationError("This site address is reserved.", code="reserved")


def validate_timezone(value):
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError("Choose a valid IANA timezone.", code="invalid") from exc


def validate_currency(value):
    if len(value) != 3 or not value.isalpha():
        raise ValidationError("Use a three-letter ISO currency code.", code="invalid")
