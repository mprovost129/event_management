import django.core.validators
from django.db import migrations, models


def update_legacy_default_theme_colors(apps, schema_editor):
    site_theme = apps.get_model("sites", "SiteTheme")
    site_theme.objects.filter(
        primary_color__iexact="#0D6EFD",
        secondary_color__iexact="#6C757D",
    ).update(primary_color="#0B1D39", secondary_color="#516543")


class Migration(migrations.Migration):
    dependencies = [
        ("sites", "0003_sitetheme_hero_heading_sitetheme_hero_image_and_more"),
    ]

    operations = [
        migrations.RunPython(
            update_legacy_default_theme_colors,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="sitetheme",
            name="primary_color",
            field=models.CharField(
                default="#0B1D39",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message=(
                            "Enter a six-digit hexadecimal color such as #336699."
                        ),
                        regex="^#[0-9A-Fa-f]{6}$",
                    )
                ],
            ),
        ),
        migrations.AlterField(
            model_name="sitetheme",
            name="secondary_color",
            field=models.CharField(
                default="#516543",
                max_length=7,
                validators=[
                    django.core.validators.RegexValidator(
                        message=(
                            "Enter a six-digit hexadecimal color such as #336699."
                        ),
                        regex="^#[0-9A-Fa-f]{6}$",
                    )
                ],
            ),
        ),
    ]
