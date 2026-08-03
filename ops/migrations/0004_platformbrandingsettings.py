from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ops", "0003_systemheartbeat"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformBrandingSettings",
            fields=[
                (
                    "singleton_key",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("show_logo_in_header", models.BooleanField(default=True)),
                ("show_name_in_header", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Platform branding settings",
                "verbose_name_plural": "Platform branding settings",
            },
        ),
    ]
