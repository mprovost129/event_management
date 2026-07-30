import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sites", "0004_alter_sitetheme_brand_colors"),
        ("events", "0003_registration_payment_status"),
        ("contacts", "0002_member_membershipplan_membersubscription_and_more"),
    ]
    operations = [
        migrations.CreateModel(
            name="Activity",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("verb", models.CharField(max_length=180)),
                ("detail", models.TextField(blank=True)),
                ("kind", models.CharField(db_index=True, default="general", max_length=40)),
                ("target_url", models.CharField(blank=True, max_length=500)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="workspace_activities", to=settings.AUTH_USER_MODEL)),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="sites.site")),
            ],
            options={"verbose_name_plural": "activities", "ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="WorkTask",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("todo", "To do"), ("in_progress", "In progress"), ("blocked", "Blocked"), ("done", "Done")], db_index=True, default="todo", max_length=20)),
                ("priority", models.CharField(choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("urgent", "Urgent")], db_index=True, default="normal", max_length=20)),
                ("due_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_work_tasks", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_work_tasks", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="work_tasks", to="events.event")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="sites.site")),
            ],
            options={"ordering": ("completed_at", "due_at", "-priority", "created_at")},
        ),
        migrations.CreateModel(
            name="TaskChecklistItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("text", models.CharField(max_length=220)),
                ("is_complete", models.BooleanField(default=False)),
                ("position", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checklist_items", to="workspace.worktask")),
            ],
            options={"ordering": ("position", "created_at")},
        ),
        migrations.CreateModel(
            name="TaskComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="workspace.worktask")),
            ],
            options={"ordering": ("created_at",)},
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("category", models.CharField(choices=[("contract", "Contract"), ("insurance", "Insurance"), ("waiver", "Waiver"), ("flyer", "Flyer"), ("policy", "Policy"), ("board", "Board document"), ("finance", "Financial or tax"), ("media", "Photo or video"), ("other", "Other")], db_index=True, default="other", max_length=30)),
                ("visibility", models.CharField(choices=[("staff", "Administrators and managers"), ("admin", "Subscriber administrator only"), ("public", "Public")], default="staff", max_length=20)),
                ("file", models.FileField(upload_to="organization-documents/%Y/%m/")),
                ("contact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents", to="contacts.contact")),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents", to="events.event")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="sites.site")),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents", to="workspace.worktask")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uploaded_workspace_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
