from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_connectedaccount_last_sync_error_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="connectedaccount",
            name="last_sync_attempted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="connectedaccount",
            name="permanent_sync_failure_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
