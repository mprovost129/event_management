from django import forms

from .models import ConsentStatus, Contact


class ContactForm(forms.ModelForm):
    tag_names = forms.CharField(
        required=False,
        label="Tags",
        help_text="Separate tags with commas.",
    )
    email_consent = forms.BooleanField(
        required=False, label="Consented to marketing email"
    )
    sms_consent = forms.BooleanField(required=False, label="Consented to SMS")

    class Meta:
        model = Contact
        fields = ("first_name", "last_name", "email", "phone", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["tag_names"].initial = ", ".join(
                self.instance.tags.values_list("name", flat=True)
            )
            self.fields["email_consent"].initial = (
                self.instance.email_consent_status == ConsentStatus.GRANTED
            )
            self.fields["sms_consent"].initial = (
                self.instance.sms_consent_status == ConsentStatus.GRANTED
            )

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
        return cleaned_data
