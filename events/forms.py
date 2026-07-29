from zoneinfo import ZoneInfo

from django import forms
from django.db import models

from contacts.models import Contact

from .models import Event, EventOccurrence, Registration
from .services import local_datetime, occurrence_starts


class EventForm(forms.ModelForm):
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    venue_name = forms.CharField(max_length=180, required=False)
    venue_address = forms.CharField(max_length=300, required=False)
    capacity = forms.IntegerField(required=False, min_value=1)

    class Meta:
        model = Event
        fields = (
            "title",
            "slug",
            "description",
            "host_name",
            "visibility",
            "status",
            "recurrence",
            "recurrence_interval",
            "recurrence_until",
            "max_guests",
        )
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Example: Friday Night Line Dance"}
            ),
            "slug": forms.TextInput(attrs={"placeholder": "friday-night-line-dance"}),
            "description": forms.Textarea(
                attrs={
                    "rows": 8,
                    "placeholder": "What should people know before they decide to attend?",
                }
            ),
            "visibility": forms.RadioSelect,
            "recurrence": forms.RadioSelect,
            "recurrence_until": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        self.fields["slug"].help_text = (
            "Used in the event's web address. Lowercase letters, numbers, and hyphens only."
        )
        self.fields["host_name"].help_text = (
            "Optional public name for the person or group hosting."
        )
        self.fields["max_guests"].label = "Guests per RSVP"
        self.fields["max_guests"].help_text = (
            "Set to 0 when each person must respond separately."
        )
        self.fields["capacity"].help_text = (
            "Optional. Leave blank when there is no attendance limit."
        )
        self.fields["recurrence_interval"].label = "Repeat every"
        if not self.is_bound:
            if not self.initial.get("host_name"):
                self.initial["host_name"] = site.display_name

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        if Event.objects.for_site(self.site).filter(slug=slug).exists():
            raise forms.ValidationError("That event URL is already in use.")
        return slug

    def clean(self):
        cleaned_data = super().clean()
        required = ("start_date", "start_time", "end_date", "end_time")
        if not all(cleaned_data.get(field) for field in required):
            return cleaned_data
        starts_at = local_datetime(
            self.site, cleaned_data["start_date"], cleaned_data["start_time"]
        )
        ends_at = local_datetime(
            self.site, cleaned_data["end_date"], cleaned_data["end_time"]
        )
        if ends_at <= starts_at:
            self.add_error("end_time", "The event must end after it starts.")
        if cleaned_data.get(
            "recurrence"
        ) != Event.Recurrence.NONE and not cleaned_data.get("recurrence_until"):
            self.add_error(
                "recurrence_until", "Choose an end date for a recurring event."
            )
        if (
            cleaned_data.get("recurrence_until")
            and cleaned_data["recurrence_until"] < cleaned_data["start_date"]
        ):
            self.add_error(
                "recurrence_until", "Recurrence cannot end before the first event."
            )
        cleaned_data["starts_at"] = starts_at
        cleaned_data["ends_at"] = ends_at
        if cleaned_data.get("recurrence") != Event.Recurrence.NONE and cleaned_data.get(
            "recurrence_until"
        ):
            try:
                for _ in occurrence_starts(
                    starts_at,
                    cleaned_data["recurrence"],
                    cleaned_data.get("recurrence_interval") or 1,
                    cleaned_data["recurrence_until"],
                ):
                    pass
            except ValueError as exc:
                self.add_error("recurrence_until", str(exc))
        return cleaned_data


class EventDetailsForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = (
            "title",
            "slug",
            "description",
            "host_name",
            "visibility",
            "status",
            "max_guests",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "visibility": forms.RadioSelect,
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        self.fields["slug"].help_text = (
            "Changing this also changes the event's public web address."
        )
        self.fields["max_guests"].label = "Guests per RSVP"

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        existing = Event.objects.for_site(self.site).filter(slug=slug)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("That event URL is already in use.")
        return slug


class OccurrenceEditForm(forms.ModelForm):
    class Scope(models.TextChoices):
        ONE = "one", "Only this occurrence"
        FUTURE = "future", "This and future occurrences"
        ALL = "all", "Every occurrence"

    scope = forms.ChoiceField(
        choices=Scope.choices, initial=Scope.ONE, widget=forms.RadioSelect
    )
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))

    class Meta:
        model = EventOccurrence
        fields = ("venue_name", "venue_address", "capacity", "status")

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        local_zone = ZoneInfo(site.timezone)
        start = self.instance.starts_at.astimezone(local_zone)
        end = self.instance.ends_at.astimezone(local_zone)
        if not self.is_bound:
            self.initial.update(
                {
                    "start_date": start.date(),
                    "start_time": start.time().replace(tzinfo=None),
                    "end_date": end.date(),
                    "end_time": end.time().replace(tzinfo=None),
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        required = ("start_date", "start_time", "end_date", "end_time")
        if not all(cleaned_data.get(field) for field in required):
            return cleaned_data
        starts_at = local_datetime(
            self.site, cleaned_data["start_date"], cleaned_data["start_time"]
        )
        ends_at = local_datetime(
            self.site, cleaned_data["end_date"], cleaned_data["end_time"]
        )
        if ends_at <= starts_at:
            self.add_error("end_time", "The event must end after it starts.")
        cleaned_data["starts_at"] = starts_at
        cleaned_data["ends_at"] = ends_at
        return cleaned_data


class ContactInvitationChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, contact):
        return f"{contact.display_name} - {contact.email}"


class InvitationForm(forms.Form):
    contacts = ContactInvitationChoiceField(
        queryset=Contact.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Only contacts with an email address can receive an invitation.",
    )

    def __init__(self, *args, site, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contacts"].queryset = (
            Contact.objects.for_site(site)
            .filter(archived_at__isnull=True)
            .exclude(email="")
        )


class GuestFieldsMixin:
    def add_guest_fields(self, max_guests):
        self.max_guests = max_guests
        self.fields["guest_count"] = forms.IntegerField(
            min_value=0,
            max_value=max_guests,
            initial=0,
            help_text=f"This event allows up to {max_guests} guest(s).",
        )
        for index in range(1, max_guests + 1):
            self.fields[f"guest_{index}_first_name"] = forms.CharField(
                max_length=100, required=False, label=f"Guest {index} first name"
            )
            self.fields[f"guest_{index}_last_name"] = forms.CharField(
                max_length=100, required=False, label=f"Guest {index} last name"
            )
            self.fields[f"guest_{index}_email"] = forms.EmailField(
                required=False, label=f"Guest {index} email"
            )
            self.fields[f"guest_{index}_phone"] = forms.CharField(
                max_length=30, required=False, label=f"Guest {index} phone"
            )

    def clean_guest_fields(self, cleaned_data):
        guest_count = (
            cleaned_data.get("guest_count", 0)
            if cleaned_data.get("response") == Registration.Response.GOING
            else 0
        )
        for index in range(1, guest_count + 1):
            for suffix in ("first_name", "last_name"):
                field = f"guest_{index}_{suffix}"
                if not cleaned_data.get(field):
                    self.add_error(
                        field, "First and last name are required for each guest."
                    )
        cleaned_data["guest_count"] = guest_count
        return cleaned_data

    def guest_data(self):
        return [
            {
                "first_name": self.cleaned_data[f"guest_{index}_first_name"],
                "last_name": self.cleaned_data[f"guest_{index}_last_name"],
                "email": self.cleaned_data.get(f"guest_{index}_email", ""),
                "phone": self.cleaned_data.get(f"guest_{index}_phone", ""),
            }
            for index in range(1, self.cleaned_data["guest_count"] + 1)
        ]


class RSVPForm(GuestFieldsMixin, forms.Form):
    response = forms.ChoiceField(choices=Registration.Response.choices)
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    email = forms.EmailField()

    def __init__(self, *args, occurrence, contact=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.contact = contact
        self.add_guest_fields(occurrence.event.max_guests)
        if contact is not None:
            for field, value in (
                ("first_name", contact.first_name),
                ("last_name", contact.last_name),
                ("email", contact.email),
            ):
                self.fields[field].initial = value
                self.fields[field].disabled = True
            registration = (
                Registration.objects.filter(occurrence=occurrence, contact=contact)
                .prefetch_related("participants")
                .first()
            )
            if registration is not None and not self.is_bound:
                self.fields["response"].initial = registration.response
                guests = list(
                    registration.participants.filter(is_primary=False, status="active")[
                        : self.max_guests
                    ]
                )
                self.fields["guest_count"].initial = len(guests)
                for index, guest in enumerate(guests, start=1):
                    for field in ("first_name", "last_name", "email", "phone"):
                        self.fields[f"guest_{index}_{field}"].initial = getattr(
                            guest, field
                        )

    def clean(self):
        return self.clean_guest_fields(super().clean())


class ManagerResponseForm(GuestFieldsMixin, forms.Form):
    contact = forms.ModelChoiceField(queryset=Contact.objects.none())
    response = forms.ChoiceField(choices=Registration.Response.choices)

    def __init__(self, *args, site, occurrence, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contact"].queryset = Contact.objects.for_site(site).filter(
            archived_at__isnull=True
        )
        self.add_guest_fields(occurrence.event.max_guests)

    def clean(self):
        return self.clean_guest_fields(super().clean())
