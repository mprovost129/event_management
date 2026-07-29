import os
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

_MISSING = object()


def env(name, default=_MISSING, *, allow_blank=False):
    value = os.environ.get(name)
    if value is None:
        if default is _MISSING:
            raise ImproperlyConfigured(
                f"Required environment variable {name} is not set."
            )
        return default
    if not allow_blank and not value.strip():
        if default is _MISSING:
            raise ImproperlyConfigured(
                f"Required environment variable {name} is blank."
            )
        return default
    return value


def env_bool(name, default=False):
    value = env(name, str(default), allow_blank=False).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(
        f"Environment variable {name} must be a boolean value, not {value!r}."
    )


def env_int(name, default):
    value = env(name, str(default), allow_blank=False)
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(
            f"Environment variable {name} must be an integer, not {value!r}."
        ) from exc


def env_list(name, default=()):
    value = os.environ.get(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def database_config_from_url(value):
    try:
        parsed = urlsplit(value)
        port = parsed.port or 5432
    except ValueError as exc:
        raise ImproperlyConfigured("DATABASE_URL is not a valid URL.") from exc
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL must use postgres or postgresql.")
    if not all((parsed.hostname, parsed.username, parsed.path.lstrip("/"))):
        raise ImproperlyConfigured(
            "DATABASE_URL must include a host, user, and database name."
        )
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": str(port),
    }
    options = dict(parse_qsl(parsed.query, keep_blank_values=False))
    if options:
        config["OPTIONS"] = options
    return config
