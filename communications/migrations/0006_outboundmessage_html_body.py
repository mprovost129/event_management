from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0005_alter_outboundmessage_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="outboundmessage",
            name="html_body",
            field=models.TextField(blank=True),
        ),
    ]
