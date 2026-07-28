from django import forms

from users.models import User

from .models import Site

TIMEZONE_CHOICES = (
    ("America/New_York", "Eastern Time"),
    ("America/Chicago", "Central Time"),
    ("America/Denver", "Mountain Time"),
    ("America/Los_Angeles", "Pacific Time"),
    ("UTC", "UTC"),
)


class SiteOnboardingForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=TIMEZONE_CHOICES)

    class Meta:
        model = Site
        fields = ("display_name", "slug", "timezone", "template_key")
        labels = {
            "display_name": "Group or brand name",
            "slug": "Site address",
            "template_key": "Starting template",
        }
        help_texts = {
            "slug": "Use lowercase letters, numbers, and hyphens.",
        }
        widgets = {
            "template_key": forms.Select(
                choices=(("classic", "Classic"), ("social", "Social"))
            )
        }

    def clean_slug(self):
        return self.cleaned_data["slug"].lower()


class ExistingManagerForm(forms.Form):
    email = forms.EmailField(
        help_text="The manager must already have a verified platform account."
    )

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"]).lower()
        try:
            user = User.objects.get(email=email, email_verified_at__isnull=False)
        except User.DoesNotExist as exc:
            raise forms.ValidationError(
                "No verified account exists for this email address."
            ) from exc
        self.user = user
        return email
