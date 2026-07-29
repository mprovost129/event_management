import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import database_config_from_url


def test_database_config_from_render_style_url():
    config = database_config_from_url(
        "postgresql://gather_hqs:p%40ssword@db.internal:5433/gather_hqs?sslmode=require"
    )

    assert config == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "gather_hqs",
        "USER": "gather_hqs",
        "PASSWORD": "p@ssword",
        "HOST": "db.internal",
        "PORT": "5433",
        "OPTIONS": {"sslmode": "require"},
    }


def test_database_config_from_url_uses_default_postgres_port():
    config = database_config_from_url(
        "postgres://gather_hqs:secret@db.internal/gather_hqs"
    )

    assert config["PORT"] == "5432"
    assert "OPTIONS" not in config


@pytest.mark.parametrize(
    "value",
    (
        "mysql://user:secret@db.internal/gather_hqs",
        "postgresql://db.internal/gather_hqs",
        "postgresql://user:secret@/gather_hqs",
        "postgresql://user:secret@db.internal",
        "postgresql://user:secret@db.internal:not-a-port/gather_hqs",
    ),
)
def test_database_config_from_url_rejects_invalid_values(value):
    with pytest.raises(ImproperlyConfigured):
        database_config_from_url(value)
