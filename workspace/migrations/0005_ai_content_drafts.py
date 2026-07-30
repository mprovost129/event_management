from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [("workspace", "0004_automation_rules"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="AIContentDraft",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content_type", models.CharField(choices=[("event_description", "Event description"), ("facebook_post", "Facebook post"), ("email_announcement", "Email announcement"), ("reminder_email", "Reminder email"), ("volunteer_plan", "Volunteer plan"), ("sponsor_outreach", "Sponsor outreach"), ("blog_post", "Blog post"), ("general", "General content")], db_index=True, default="general", max_length=40)),
                ("title", models.CharField(max_length=180)),
                ("instructions", models.TextField()),
                ("context", models.TextField(blank=True)),
                ("output", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("generated", "Generated"), ("failed", "Failed")], db_index=True, default="draft", max_length=20)),
                ("provider", models.CharField(blank=True, max_length=40)),
                ("model_name", models.CharField(blank=True, max_length=80)),
                ("error_message", models.TextField(blank=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_content_drafts", to=settings.AUTH_USER_MODEL)),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="sites.site")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
