from django.db import migrations, models
import uuid
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("contacts", "0001_initial"), ("events", "0001_initial"), ("workspace", "0002_volunteers_sponsors")]
    operations = [
        migrations.CreateModel(
            name="IntakeForm",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=180)),
                ("slug", models.SlugField(max_length=80)),
                ("kind", models.CharField(choices=[("general", "General form"), ("registration", "Registration form"), ("waiver", "Waiver or release"), ("volunteer", "Volunteer interest")], db_index=True, default="general", max_length=20)),
                ("introduction", models.TextField(blank=True)),
                ("confirmation_message", models.TextField(default="Thank you. Your response has been received.")),
                ("fields", models.JSONField(default=list, help_text="Ordered field definitions used to build the public form.")),
                ("require_signature", models.BooleanField(default=False)),
                ("agreement_text", models.TextField(blank=True)),
                ("create_or_update_contact", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("closes_at", models.DateTimeField(blank=True, null=True)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="intake_forms", to="events.event")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="sites.site")),
            ],
            options={"ordering": ("title",)},
        ),
        migrations.CreateModel(
            name="IntakeSubmission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("response_data", models.JSONField(default=dict)),
                ("submitter_name", models.CharField(blank=True, max_length=180)),
                ("submitter_email", models.EmailField(blank=True, max_length=254)),
                ("signature_name", models.CharField(blank=True, max_length=180)),
                ("agreed_at", models.DateTimeField(blank=True, null=True)),
                ("source_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=500)),
                ("contact", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="intake_submissions", to="contacts.contact")),
                ("intake_form", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="submissions", to="workspace.intakeform")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="sites.site")),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(model_name="intakeform", constraint=models.UniqueConstraint(fields=("site", "slug"), name="workspace_unique_intake_form_slug")),
    ]
