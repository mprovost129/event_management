from zoneinfo import ZoneInfo

from django import forms
from django.db import models

from .models import Event, EventOccurrence
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
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 8}),
            "recurrence_until": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)

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
        fields = ("title", "slug", "description", "host_name", "visibility", "status")
        widgets = {"description": forms.Textarea(attrs={"rows": 8})}

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)

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

    scope = forms.ChoiceField(choices=Scope.choices, initial=Scope.ONE)
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
