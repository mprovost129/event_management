from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from sites.models import SiteOwnedModel


class Activity(SiteOwnedModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workspace_activities",
    )
    verb = models.CharField(max_length=180)
    detail = models.TextField(blank=True)
    kind = models.CharField(max_length=40, default="general", db_index=True)
    target_url = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = "activities"
        indexes = [
            models.Index(
                fields=("site", "kind", "-created_at"),
                name="ws_activity_site_kind_time",
            )
        ]

    def __str__(self):
        return self.verb


class WorkTask(SiteOwnedModel):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="work_tasks",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_work_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_work_tasks",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TODO, db_index=True
    )
    priority = models.CharField(
        max_length=20, choices=Priority.choices, default=Priority.NORMAL, db_index=True
    )
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("completed_at", "due_at", "-priority", "created_at")
        indexes = [
            models.Index(
                fields=("site", "status", "due_at"),
                name="ws_task_site_status_due",
            )
        ]

    def clean(self):
        super().clean()
        if self.event_id and self.event.site_id != self.site_id:
            raise ValidationError("The task and event must belong to the same site.")
        if (
            self.assignee_id
            and not self.assignee.site_roles.filter(
                site_id=self.site_id, is_active=True
            ).exists()
        ):
            raise ValidationError(
                "The assignee must be an active administrator or manager for this site."
            )

    def save(self, *args, **kwargs):
        if self.status == self.Status.DONE and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.status != self.Status.DONE:
            self.completed_at = None
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return bool(
            self.due_at
            and self.status != self.Status.DONE
            and self.due_at < timezone.now()
        )

    def __str__(self):
        return self.title


class TaskChecklistItem(models.Model):
    task = models.ForeignKey(
        WorkTask, on_delete=models.CASCADE, related_name="checklist_items"
    )
    text = models.CharField(max_length=220)
    is_complete = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "created_at")


class TaskComment(models.Model):
    task = models.ForeignKey(
        WorkTask, on_delete=models.CASCADE, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)


class Document(SiteOwnedModel):
    class Category(models.TextChoices):
        CONTRACT = "contract", "Contract"
        INSURANCE = "insurance", "Insurance"
        WAIVER = "waiver", "Waiver"
        FLYER = "flyer", "Flyer"
        POLICY = "policy", "Policy"
        BOARD = "board", "Board document"
        FINANCE = "finance", "Financial or tax"
        MEDIA = "media", "Photo or video"
        OTHER = "other", "Other"

    class Visibility(models.TextChoices):
        STAFF = "staff", "Administrators and managers"
        ADMIN = "admin", "Subscriber administrator only"
        PUBLIC = "public", "Public"

    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=30, choices=Category.choices, default=Category.OTHER, db_index=True
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.STAFF
    )
    file = models.FileField(upload_to="organization-documents/%Y/%m/")
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    task = models.ForeignKey(
        WorkTask,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_workspace_documents",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("site", "category", "-created_at"),
                name="ws_doc_site_cat_time",
            )
        ]

    def clean(self):
        super().clean()
        for related in (self.event, self.contact, self.task):
            if related and related.site_id != self.site_id:
                raise ValidationError("Linked records must belong to the same site.")

    def __str__(self):
        return self.title


class VolunteerProfile(SiteOwnedModel):
    class Status(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    contact = models.OneToOneField(
        "contacts.Contact", on_delete=models.CASCADE, related_name="volunteer_profile"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    skills = models.TextField(
        blank=True, help_text="Comma-separated skills or qualifications."
    )
    availability = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=180, blank=True)
    emergency_phone = models.CharField(max_length=30, blank=True)
    background_check_expires_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("contact__last_name", "contact__first_name")
        indexes = [
            models.Index(fields=("site", "status"), name="ws_volunteer_site_status")
        ]

    def clean(self):
        super().clean()
        if self.contact_id and self.contact.site_id != self.site_id:
            raise ValidationError(
                "The volunteer and contact must belong to the same site."
            )

    @property
    def total_hours(self):
        if hasattr(self, "total_hours_value"):
            return self.total_hours_value
        return sum((entry.hours for entry in self.hour_entries.all()), 0)

    def __str__(self):
        return str(self.contact)


class VolunteerShift(SiteOwnedModel):
    title = models.CharField(max_length=180)
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="volunteer_shifts",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    location = models.CharField(max_length=180, blank=True)
    capacity = models.PositiveSmallIntegerField(default=1)
    instructions = models.TextField(blank=True)

    class Meta:
        ordering = ("starts_at", "title")

    def clean(self):
        super().clean()
        if self.ends_at <= self.starts_at:
            raise ValidationError("A volunteer shift must end after it starts.")
        if self.event_id and self.event.site_id != self.site_id:
            raise ValidationError("The shift and event must belong to the same site.")

    @property
    def open_spots(self):
        return max(
            self.capacity
            - self.assignments.exclude(
                status=VolunteerAssignment.Status.CANCELED
            ).count(),
            0,
        )

    def __str__(self):
        return self.title


class VolunteerAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        CONFIRMED = "confirmed", "Confirmed"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No show"
        CANCELED = "canceled", "Canceled"

    shift = models.ForeignKey(
        VolunteerShift, on_delete=models.CASCADE, related_name="assignments"
    )
    volunteer = models.ForeignKey(
        VolunteerProfile, on_delete=models.CASCADE, related_name="assignments"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ASSIGNED, db_index=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("shift", "volunteer"), name="workspace_one_volunteer_per_shift"
            )
        ]
        ordering = ("shift__starts_at", "volunteer__contact__last_name")

    def clean(self):
        super().clean()
        if (
            self.shift_id
            and self.volunteer_id
            and self.shift.site_id != self.volunteer.site_id
        ):
            raise ValidationError(
                "The volunteer and shift must belong to the same site."
            )


class VolunteerHourEntry(SiteOwnedModel):
    volunteer = models.ForeignKey(
        VolunteerProfile, on_delete=models.CASCADE, related_name="hour_entries"
    )
    assignment = models.ForeignKey(
        VolunteerAssignment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="hour_entries",
    )
    service_date = models.DateField(default=timezone.localdate)
    hours = models.DecimalField(max_digits=6, decimal_places=2)
    description = models.CharField(max_length=220, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_volunteer_hours",
    )

    class Meta:
        ordering = ("-service_date", "-created_at")

    def clean(self):
        super().clean()
        if self.hours <= 0:
            raise ValidationError("Volunteer hours must be greater than zero.")
        if self.volunteer_id and self.volunteer.site_id != self.site_id:
            raise ValidationError(
                "The hour entry and volunteer must belong to the same site."
            )
        if self.assignment_id and self.assignment.shift.site_id != self.site_id:
            raise ValidationError(
                "The hour entry and assignment must belong to the same site."
            )


class Sponsor(SiteOwnedModel):
    class Status(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=180)
    contact_name = models.CharField(max_length=180, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="sponsor-logos/%Y/%m/", blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROSPECT, db_index=True
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(fields=("site", "status"), name="ws_sponsor_site_status")
        ]

    def __str__(self):
        return self.name


class Sponsorship(SiteOwnedModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        COMMITTED = "committed", "Committed"
        INVOICED = "invoiced", "Invoiced"
        PAID = "paid", "Paid"
        CANCELED = "canceled", "Canceled"

    sponsor = models.ForeignKey(
        Sponsor, on_delete=models.CASCADE, related_name="sponsorships"
    )
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sponsorships",
    )
    level = models.CharField(max_length=100, blank=True)
    amount_cents = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PROPOSED, db_index=True
    )
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    benefits = models.TextField(blank=True)
    invoice_reference = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.sponsor_id and self.sponsor.site_id != self.site_id:
            raise ValidationError(
                "The sponsorship and sponsor must belong to the same site."
            )
        if self.event_id and self.event.site_id != self.site_id:
            raise ValidationError(
                "The sponsorship and event must belong to the same site."
            )
        if self.starts_on and self.ends_on and self.ends_on < self.starts_on:
            raise ValidationError(
                "The sponsorship end date cannot be before its start date."
            )

    @property
    def amount_display(self):
        return self.amount_cents / 100


class IntakeForm(SiteOwnedModel):
    class Kind(models.TextChoices):
        GENERAL = "general", "General form"
        REGISTRATION = "registration", "Registration form"
        WAIVER = "waiver", "Waiver or release"
        VOLUNTEER = "volunteer", "Volunteer interest"

    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=80)
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.GENERAL, db_index=True
    )
    introduction = models.TextField(blank=True)
    confirmation_message = models.TextField(
        default="Thank you. Your response has been received."
    )
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intake_forms",
    )
    fields = models.JSONField(
        default=list,
        help_text="Ordered field definitions used to build the public form.",
    )
    require_signature = models.BooleanField(default=False)
    agreement_text = models.TextField(blank=True)
    create_or_update_contact = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    closes_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=("site", "slug"), name="workspace_unique_intake_form_slug"
            )
        ]
        indexes = [
            models.Index(fields=("site", "is_active"), name="ws_form_site_active")
        ]

    def clean(self):
        super().clean()
        if self.event_id and self.event.site_id != self.site_id:
            raise ValidationError("The form and event must belong to the same site.")
        if self.require_signature and not self.agreement_text.strip():
            raise ValidationError(
                {
                    "agreement_text": "Agreement text is required when a signature is required."
                }
            )
        if not isinstance(self.fields, list):
            raise ValidationError(
                {"fields": "Fields must be a list of field definitions."}
            )
        allowed_types = {
            "text",
            "email",
            "phone",
            "textarea",
            "number",
            "date",
            "select",
            "checkbox",
        }
        seen = set()
        for index, field in enumerate(self.fields, start=1):
            if not isinstance(field, dict):
                raise ValidationError({"fields": f"Field {index} must be an object."})
            key = str(field.get("key", "")).strip()
            label = str(field.get("label", "")).strip()
            field_type = str(field.get("type", "text")).strip()
            if not key or not label:
                raise ValidationError(
                    {"fields": f"Field {index} requires a key and label."}
                )
            if key in seen:
                raise ValidationError({"fields": f"Field key '{key}' is duplicated."})
            if field_type not in allowed_types:
                raise ValidationError(
                    {"fields": f"Field '{key}' uses an unsupported type."}
                )
            seen.add(key)

    @property
    def accepts_responses(self):
        return self.is_active and (
            not self.closes_at or self.closes_at > timezone.now()
        )

    def __str__(self):
        return self.title


class IntakeSubmission(SiteOwnedModel):
    intake_form = models.ForeignKey(
        IntakeForm, on_delete=models.CASCADE, related_name="submissions"
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intake_submissions",
    )
    response_data = models.JSONField(default=dict)
    submitter_name = models.CharField(max_length=180, blank=True)
    submitter_email = models.EmailField(blank=True)
    signature_name = models.CharField(max_length=180, blank=True)
    agreed_at = models.DateTimeField(null=True, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.intake_form_id and self.intake_form.site_id != self.site_id:
            raise ValidationError(
                "The submission and form must belong to the same site."
            )
        if self.contact_id and self.contact.site_id != self.site_id:
            raise ValidationError(
                "The submission and contact must belong to the same site."
            )
        if (
            self.intake_form_id
            and self.intake_form.require_signature
            and not self.signature_name.strip()
        ):
            raise ValidationError({"signature_name": "A signature is required."})

    def __str__(self):
        return f"{self.intake_form}: {self.submitter_name or self.submitter_email or self.created_at}"


class AutomationRule(SiteOwnedModel):
    class Trigger(models.TextChoices):
        FORM_SUBMITTED = "form_submitted", "Form submitted"
        CONTACT_CREATED = "contact_created", "Contact created"
        RSVP_RECEIVED = "rsvp_received", "RSVP received"
        TASK_OVERDUE = "task_overdue", "Task overdue"
        MANUAL = "manual", "Manual run"

    class Action(models.TextChoices):
        CREATE_TASK = "create_task", "Create a task"
        ADD_CONTACT_TAG = "add_contact_tag", "Add a contact tag"
        RECORD_ACTIVITY = "record_activity", "Record activity"

    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    trigger = models.CharField(max_length=30, choices=Trigger.choices, db_index=True)
    action = models.CharField(max_length=30, choices=Action.choices)
    trigger_config = models.JSONField(default=dict, blank=True)
    action_config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_workspace_automations",
    )

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(
                fields=("site", "is_active", "trigger"),
                name="ws_auto_site_active_trigger",
            )
        ]

    def clean(self):
        super().clean()
        if not isinstance(self.trigger_config, dict):
            raise ValidationError(
                {"trigger_config": "Trigger configuration must be an object."}
            )
        if not isinstance(self.action_config, dict):
            raise ValidationError(
                {"action_config": "Action configuration must be an object."}
            )
        if (
            self.action == self.Action.CREATE_TASK
            and not str(self.action_config.get("title", "")).strip()
        ):
            raise ValidationError({"action_config": "Task actions require a title."})
        if (
            self.action == self.Action.ADD_CONTACT_TAG
            and not str(self.action_config.get("tag", "")).strip()
        ):
            raise ValidationError(
                {"action_config": "Contact tag actions require a tag."}
            )

    def __str__(self):
        return self.name


class AutomationRun(SiteOwnedModel):
    class Status(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    rule = models.ForeignKey(
        AutomationRule, on_delete=models.CASCADE, related_name="runs"
    )
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    trigger_data = models.JSONField(default=dict, blank=True)
    result_detail = models.TextField(blank=True)
    error_detail = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("site", "status", "-created_at"),
                name="ws_run_site_status_time",
            )
        ]

    def clean(self):
        super().clean()
        if self.rule_id and self.rule.site_id != self.site_id:
            raise ValidationError(
                "The automation run and rule must belong to the same site."
            )


class AIContentDraft(SiteOwnedModel):
    class ContentType(models.TextChoices):
        EVENT_DESCRIPTION = "event_description", "Event description"
        FACEBOOK_POST = "facebook_post", "Facebook post"
        EMAIL_ANNOUNCEMENT = "email_announcement", "Email announcement"
        REMINDER_EMAIL = "reminder_email", "Reminder email"
        VOLUNTEER_PLAN = "volunteer_plan", "Volunteer plan"
        SPONSOR_OUTREACH = "sponsor_outreach", "Sponsor outreach"
        BLOG_POST = "blog_post", "Blog post"
        GENERAL = "general", "General content"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        GENERATED = "generated", "Generated"
        FAILED = "failed", "Failed"

    content_type = models.CharField(
        max_length=40,
        choices=ContentType.choices,
        default=ContentType.GENERAL,
        db_index=True,
    )
    title = models.CharField(max_length=180)
    instructions = models.TextField()
    context = models.TextField(blank=True)
    output = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    provider = models.CharField(max_length=40, blank=True)
    model_name = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_content_drafts",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("site", "status", "-created_at"),
                name="ws_ai_site_status_time",
            )
        ]

    def __str__(self):
        return self.title
