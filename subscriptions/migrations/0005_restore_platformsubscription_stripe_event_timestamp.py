from django.db import migrations


def ensure_stripe_event_timestamp_column(apps, schema_editor):
    platform_subscription = apps.get_model("subscriptions", "PlatformSubscription")
    table_name = platform_subscription._meta.db_table
    field = platform_subscription._meta.get_field("last_stripe_event_created_at")

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }

    if field.column not in columns:
        schema_editor.add_field(platform_subscription, field)


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0004_platformsubscription_last_stripe_event_created_at"),
    ]

    operations = [
        migrations.RunPython(
            ensure_stripe_event_timestamp_column,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
