import json
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from contacts.models import Contact
from events.models import Event

from .models import (
    AIContentDraft,
    AutomationRule,
    Document,
    IntakeForm,
    Sponsor,
    Sponsorship,
    TaskChecklistItem,
    TaskComment,
    VolunteerAssignment,
    VolunteerHourEntry,
    VolunteerProfile,
    VolunteerShift,
    WorkTask,
)


class TaskForm(forms.ModelForm):
    due_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = WorkTask
        fields = (
            "title",
            "description",
            "event",
            "assignee",
            "status",
            "priority",
            "due_at",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.for_site(site).order_by("title")
        self.fields["assignee"].queryset = (
            get_user_model()
            .objects.filter(site_roles__site=site, site_roles__is_active=True)
            .distinct()
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "form-control"
                if not isinstance(field.widget, forms.Select)
                else "form-select",
            )


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = TaskChecklistItem
        fields = ("text",)


class CommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Add a comment…"})
        }


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = (
            "title",
            "description",
            "category",
            "visibility",
            "file",
            "event",
            "contact",
            "task",
        )
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, site, can_manage_admin_documents=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.for_site(site).order_by("title")
        self.fields["contact"].queryset = Contact.objects.for_site(site).filter(
            archived_at__isnull=True
        )
        self.fields["task"].queryset = WorkTask.objects.for_site(site).exclude(
            status=WorkTask.Status.DONE
        )
        if not can_manage_admin_documents:
            self.fields["visibility"].choices = [
                choice
                for choice in self.fields["visibility"].choices
                if choice[0] != Document.Visibility.ADMIN
            ]
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "form-control"
                if not isinstance(field.widget, forms.Select)
                else "form-select",
            )

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if not upload:
            return upload
        extension = Path(upload.name).suffix.lower().lstrip(".")
        if extension not in settings.DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS:
            allowed = ", ".join(
                f".{item}" for item in settings.DOCUMENT_UPLOAD_ALLOWED_EXTENSIONS
            )
            raise ValidationError(f"This file type is not allowed. Use: {allowed}.")
        if upload.size > settings.DOCUMENT_UPLOAD_MAX_BYTES:
            limit_mb = settings.DOCUMENT_UPLOAD_MAX_BYTES / (1024 * 1024)
            raise ValidationError(f"Files must be {limit_mb:g} MB or smaller.")
        return upload


class VolunteerProfileForm(forms.ModelForm):
    class Meta:
        model = VolunteerProfile
        fields = (
            "contact",
            "status",
            "skills",
            "availability",
            "emergency_contact",
            "emergency_phone",
            "background_check_expires_on",
            "notes",
        )
        widgets = {
            "background_check_expires_on": forms.DateInput(attrs={"type": "date"}),
            "skills": forms.Textarea(attrs={"rows": 2}),
            "availability": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].queryset = (
            Contact.objects.for_site(site)
            .filter(archived_at__isnull=True)
            .exclude(volunteer_profile__isnull=False)
        )
        if self.instance.pk:
            self.fields["contact"].queryset = Contact.objects.for_site(site).filter(
                pk=self.instance.contact_id
            )
        _style(self)


class VolunteerShiftForm(forms.ModelForm):
    starts_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    ends_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = VolunteerShift
        fields = (
            "title",
            "event",
            "starts_at",
            "ends_at",
            "location",
            "capacity",
            "instructions",
        )
        widgets = {"instructions": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.for_site(site).order_by("title")
        _style(self)


class VolunteerAssignmentForm(forms.ModelForm):
    class Meta:
        model = VolunteerAssignment
        fields = ("volunteer", "status", "notes")

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["volunteer"].queryset = (
            VolunteerProfile.objects.for_site(site)
            .filter(status=VolunteerProfile.Status.ACTIVE)
            .select_related("contact")
        )
        _style(self)


class VolunteerHourForm(forms.ModelForm):
    class Meta:
        model = VolunteerHourEntry
        fields = ("service_date", "hours", "description", "assignment")
        widgets = {"service_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, site, volunteer, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignment"].queryset = VolunteerAssignment.objects.filter(
            volunteer=volunteer, shift__site=site
        ).select_related("shift")
        _style(self)


class SponsorForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        fields = (
            "name",
            "contact_name",
            "email",
            "phone",
            "website",
            "logo",
            "status",
            "notes",
        )
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class SponsorshipForm(forms.ModelForm):
    amount = forms.DecimalField(
        min_value=0, decimal_places=2, max_digits=12, label="Amount ($)"
    )

    class Meta:
        model = Sponsorship
        fields = (
            "event",
            "level",
            "status",
            "starts_on",
            "ends_on",
            "benefits",
            "invoice_reference",
        )
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "ends_on": forms.DateInput(attrs={"type": "date"}),
            "benefits": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["event"].queryset = Event.objects.for_site(site).order_by("title")
        if self.instance.pk:
            self.fields["amount"].initial = self.instance.amount_cents / 100
        _style(self)

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.amount_cents = int(self.cleaned_data["amount"] * 100)
        if commit:
            obj.save()
        return obj


def _style(form):
    for field in form.fields.values():
        field.widget.attrs.setdefault(
            "class",
            "form-control"
            if not isinstance(field.widget, forms.Select)
            else "form-select",
        )


class IntakeFormBuilderForm(forms.ModelForm):
    fields_json = forms.CharField(
        label="Fields",
        required=False,
        widget=forms.Textarea(attrs={"rows": 12}),
        help_text='Enter a JSON list. Example: [{"key":"first_name","label":"First name","type":"text","required":true}]',
    )
    closes_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = IntakeForm
        fields = (
            "title",
            "slug",
            "kind",
            "introduction",
            "confirmation_message",
            "event",
            "require_signature",
            "agreement_text",
            "create_or_update_contact",
            "is_active",
            "closes_at",
        )
        widgets = {
            "introduction": forms.Textarea(attrs={"rows": 4}),
            "confirmation_message": forms.Textarea(attrs={"rows": 3}),
            "agreement_text": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.site = site
        self.fields["event"].queryset = Event.objects.for_site(site).order_by("title")
        if self.instance.pk:
            self.fields["fields_json"].initial = json.dumps(
                self.instance.fields, indent=2
            )
        else:
            self.fields["fields_json"].initial = json.dumps(
                [
                    {
                        "key": "first_name",
                        "label": "First name",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "key": "last_name",
                        "label": "Last name",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "key": "email",
                        "label": "Email",
                        "type": "email",
                        "required": True,
                    },
                ],
                indent=2,
            )
        _style(self)

    def clean_slug(self):
        value = slugify(
            self.cleaned_data.get("slug") or self.cleaned_data.get("title", "")
        )
        if not value:
            raise ValidationError("Enter a usable slug.")
        qs = IntakeForm.objects.for_site(self.site).filter(slug=value)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                "A form with this slug already exists for this organization."
            )
        return value

    def clean_fields_json(self):
        raw = self.cleaned_data.get("fields_json", "").strip() or "[]"
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"Invalid JSON: {exc.msg} on line {exc.lineno}."
            ) from exc
        if not isinstance(value, list):
            raise ValidationError("Fields must be a JSON list.")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.fields = self.cleaned_data["fields_json"]
        obj.site = self.site
        obj.full_clean()
        if commit:
            obj.save()
        return obj


def build_public_intake_form(intake_form, data=None):
    dynamic_fields = {}
    for definition in intake_form.fields:
        key = definition["key"]
        label = definition["label"]
        required = bool(definition.get("required", False))
        help_text = definition.get("help_text", "")
        field_type = definition.get("type", "text")
        if field_type == "textarea":
            field = forms.CharField(
                label=label,
                required=required,
                help_text=help_text,
                widget=forms.Textarea(attrs={"rows": 4}),
            )
        elif field_type == "email":
            field = forms.EmailField(
                label=label, required=required, help_text=help_text
            )
        elif field_type == "number":
            field = forms.DecimalField(
                label=label, required=required, help_text=help_text
            )
        elif field_type == "date":
            field = forms.DateField(
                label=label,
                required=required,
                help_text=help_text,
                widget=forms.DateInput(attrs={"type": "date"}),
            )
        elif field_type == "select":
            choices = [
                (str(option), str(option)) for option in definition.get("options", [])
            ]
            field = forms.ChoiceField(
                label=label, required=required, help_text=help_text, choices=choices
            )
        elif field_type == "checkbox":
            field = forms.BooleanField(
                label=label, required=required, help_text=help_text
            )
        else:
            input_type = "tel" if field_type == "phone" else "text"
            field = forms.CharField(
                label=label,
                required=required,
                help_text=help_text,
                widget=forms.TextInput(attrs={"type": input_type}),
            )
        field.widget.attrs.setdefault(
            "class", "form-check-input" if field_type == "checkbox" else "form-control"
        )
        dynamic_fields[key] = field
    if intake_form.require_signature:
        dynamic_fields["signature_name"] = forms.CharField(
            label="Electronic signature",
            help_text="Type your full legal name.",
            widget=forms.TextInput(attrs={"class": "form-control"}),
        )
        dynamic_fields["agreement_accepted"] = forms.BooleanField(
            label="I have read and agree to the statement above.",
            widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        )
    form_class = type("PublicIntakeResponseForm", (forms.Form,), dynamic_fields)
    return form_class(data=data)


class AutomationRuleForm(forms.ModelForm):
    trigger_config_json = forms.CharField(
        required=False,
        label="Trigger settings (JSON)",
        widget=forms.Textarea(
            attrs={"rows": 5, "placeholder": '{"form_id": "optional-form-uuid"}'}
        ),
    )
    action_config_json = forms.CharField(
        required=False,
        label="Action settings (JSON)",
        widget=forms.Textarea(
            attrs={
                "rows": 6,
                "placeholder": '{"title": "Follow up with {{ submitter_name }}", "priority": "normal"}',
            }
        ),
    )

    class Meta:
        model = AutomationRule
        fields = ("name", "description", "trigger", "action", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["trigger_config_json"].initial = json.dumps(
                self.instance.trigger_config, indent=2
            )
            self.fields["action_config_json"].initial = json.dumps(
                self.instance.action_config, indent=2
            )
        _style(self)

    def _json(self, field):
        raw = self.cleaned_data.get(field, "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f"Invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise forms.ValidationError("Configuration must be a JSON object.")
        return value

    def clean_trigger_config_json(self):
        return self._json("trigger_config_json")

    def clean_action_config_json(self):
        return self._json("action_config_json")

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.site = self.site
        obj.trigger_config = self.cleaned_data["trigger_config_json"]
        obj.action_config = self.cleaned_data["action_config_json"]
        obj.full_clean()
        if commit:
            obj.save()
        return obj


class AIContentDraftForm(forms.ModelForm):
    class Meta:
        model = AIContentDraft
        fields = ("content_type", "title", "instructions", "context")
        widgets = {
            "instructions": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Describe the content you need, the audience, tone, and important details.",
                }
            ),
            "context": forms.Textarea(
                attrs={
                    "rows": 7,
                    "placeholder": "Optional source details such as dates, pricing, location, event information, or existing copy.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)
