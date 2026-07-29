from django import forms
from django.db import models
from django.utils import timezone

from .models import ConsentStatus, Contact, Member


class ContactForm(forms.ModelForm):
    class MemberTracking(models.TextChoices):
        CONTACT_ONLY = "contact_only", "Contact only"
        ACTIVE = "active", "Active member"
        INACTIVE = "inactive", "Inactive member"

    tag_names = forms.CharField(
        required=False,
        label="Tags",
        help_text="Separate tags with commas.",
    )
    email_consent = forms.BooleanField(
        required=False, label="Consented to marketing email"
    )
    sms_consent = forms.BooleanField(required=False, label="Consented to SMS")
    member_tracking = forms.ChoiceField(
        choices=MemberTracking.choices,
        initial=MemberTracking.CONTACT_ONLY,
        label="Member status",
        help_text="Members are still contacts and must RSVP separately to events.",
    )
    member_starts_on = forms.DateField(
        required=False,
        label="Membership starts",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    member_ends_on = forms.DateField(
        required=False,
        label="Membership ends",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    member_notes = forms.CharField(
        required=False,
        label="Membership notes",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        model = Contact
        fields = ("first_name", "last_name", "email", "phone", "notes")
        widgets = {
            "notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Private notes for site managers only.",
                }
            )
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        self.member = None
        if not self.instance._state.adding:
            self.fields["tag_names"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )
            self.fields["email_consent"].initial = (
                self.instance.email_consent_status == ConsentStatus.GRANTED
            )
            self.fields["sms_consent"].initial = (
                self.instance.sms_consent_status == ConsentStatus.GRANTED
            )
            self.member = Member.objects.filter(contact=self.instance).first()
            if self.member is not None:
                self.fields["member_tracking"].initial = (
                    self.member.administrative_status
                )
                self.fields["member_starts_on"].initial = self.member.starts_on
                self.fields["member_ends_on"].initial = self.member.ends_on
                self.fields["member_notes"].initial = self.member.notes

    def clean_email(self):
        email = self.cleaned_data["email"].strip().casefold()
        if not email:
            return ""
        existing = Contact.objects.for_site(self.site).filter(normalized_email=email)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("A contact with that email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("email_consent") and not cleaned_data.get("email"):
            self.add_error("email", "An email address is required for email consent.")
        if cleaned_data.get("sms_consent") and not cleaned_data.get("phone"):
            self.add_error("phone", "A phone number is required for SMS consent.")
        member_tracking = cleaned_data.get("member_tracking")
        member_starts_on = cleaned_data.get("member_starts_on")
        member_ends_on = cleaned_data.get("member_ends_on")
        if member_tracking != self.MemberTracking.CONTACT_ONLY and not member_starts_on:
            self.add_error("member_starts_on", "Choose when this membership starts.")
        if member_starts_on and member_ends_on and member_ends_on < member_starts_on:
            self.add_error(
                "member_ends_on", "Membership cannot end before it starts."
            )
        if (
            member_tracking == self.MemberTracking.CONTACT_ONLY
            and self.member is not None
            and self.member.subscriptions.exists()
        ):
            self.add_error(
                "member_tracking",
                "This member has subscription history. Mark them inactive instead.",
            )
        return cleaned_data
