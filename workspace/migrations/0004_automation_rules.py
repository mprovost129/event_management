from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("workspace", "0003_forms_waivers"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AutomationRule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("trigger", models.CharField(choices=[("form_submitted", "Form submitted"), ("contact_created", "Contact created"), ("rsvp_received", "RSVP received"), ("task_overdue", "Task overdue"), ("manual", "Manual run")], db_index=True, max_length=30)),
                ("action", models.CharField(choices=[("create_task", "Create a task"), ("add_contact_tag", "Add a contact tag"), ("record_activity", "Record activity")], max_length=30)),
                ("trigger_config", models.JSONField(blank=True, default=dict)),
                ("action_config", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_workspace_automations", to=settings.AUTH_USER_MODEL)),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="automation_rules", to="sites.site")),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="AutomationRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("succeeded", "Succeeded"), ("skipped", "Skipped"), ("failed", "Failed")], db_index=True, max_length=20)),
                ("trigger_data", models.JSONField(blank=True, default=dict)),
                ("result_detail", models.TextField(blank=True)),
                ("error_detail", models.TextField(blank=True)),
                ("rule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="runs", to="workspace.automationrule")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="automation_runs", to="sites.site")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
