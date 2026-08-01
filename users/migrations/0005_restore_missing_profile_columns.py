from django.db import migrations


def restore_missing_profile_columns(apps, schema_editor):
    """Recreate profile columns if an environment previously dropped them.

    This keeps production safe after the short-lived rollback commit that
    removed profile fields from the model and database in some deployments.
    """

    user_model = apps.get_model("users", "User")
    table_name = user_model._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    for field_name in (
        "username",
        "avatar",
        "mailing_address_line1",
        "mailing_address_line2",
        "mailing_city",
        "mailing_state",
        "mailing_postal_code",
        "mailing_country",
    ):
        if field_name in existing_columns:
            continue
        schema_editor.add_field(user_model, user_model._meta.get_field(field_name))


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0004_user_profile_fields"),
    ]

    operations = [
        migrations.RunPython(
            restore_missing_profile_columns,
            reverse_code=migrations.RunPython.noop,
        )
    ]
