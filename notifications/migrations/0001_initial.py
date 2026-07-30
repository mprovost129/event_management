# Generated manually for Gather HQs.
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sites", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("kind", models.CharField(choices=[("rsvp", "Event response"), ("event_update", "Event update"), ("payment", "Payment update"), ("team", "Team update"), ("system", "System update")], max_length=30)),
                ("title", models.CharField(max_length=180)),
                ("message", models.TextField()),
                ("action_url", models.CharField(blank=True, max_length=500)),
                ("dedupe_key", models.CharField(blank=True, max_length=255)),
                ("read_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="sites.site")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.UniqueConstraint(condition=models.Q(("dedupe_key", ""), _negated=True), fields=("recipient", "dedupe_key"), name="notifications_unique_recipient_dedupe"),
        ),
    ]
