from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_restore_missing_profile_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_subscription_exempt",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When enabled, this user can manage organizations without an active paid "
                    "platform subscription."
                ),
            ),
        ),
    ]
