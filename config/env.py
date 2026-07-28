import os

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
