from django import forms

from contacts.models import ContactTag
from events.models import EventOccurrence, Registration

from .models import Campaign


class CampaignForm(forms.ModelForm):
    response_filter = forms.ChoiceField(
        choices=(("", "Choose a response"), *Registration.Response.choices),
        required=False,
    )

    class Meta:
        model = Campaign
        fields = (
            "name",
            "channel",
            "subject",
            "body",
            "audience",
            "audience_tag",
            "audience_occurrence",
            "response_filter",
            "scheduled_for",
        )
        widgets = {
            "channel": forms.RadioSelect,
            "body": forms.Textarea(
                attrs={"rows": 14, "placeholder": "Write your update here..."}
            ),
            "scheduled_for": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        self.fields["audience_tag"].queryset = ContactTag.objects.for_site(site)
        self.fields["audience_tag"].required = False
        self.fields["audience_occurrence"].queryset = (
            EventOccurrence.objects.for_site(site)
            .select_related("event")
            .order_by("-starts_at")
        )
        self.fields["audience_occurrence"].required = False
        self.fields["name"].label = "Campaign name"
        self.fields[
            "name"
        ].help_text = "An internal label to help your team find this campaign later."
        self.fields[
            "subject"
        ].help_text = (
            "Required for email newsletters and not used for SMS announcements."
        )
        self.fields[
            "audience"
        ].help_text = (
            "Only contacts with consent for the selected channel can receive it."
        )
        self.fields["scheduled_for"].label = "Send later"
        self.fields[
            "scheduled_for"
        ].help_text = (
            f"Optional. Leave blank to send after review. Times use {site.timezone}."
        )

    def clean(self):
        cleaned = super().clean()
        audience = cleaned.get("audience")
        if audience != Campaign.Audience.TAG:
            cleaned["audience_tag"] = None
        if audience not in (
            Campaign.Audience.EVENT_INVITEES,
            Campaign.Audience.RESPONSE,
        ):
            cleaned["audience_occurrence"] = None
        if audience != Campaign.Audience.RESPONSE:
            cleaned["response_filter"] = ""
        if (
            cleaned.get("channel") == Campaign.Channel.EMAIL
            and not cleaned.get("subject", "").strip()
        ):
            self.add_error("subject", "Email campaigns require a subject.")
        if audience == Campaign.Audience.TAG and not cleaned.get("audience_tag"):
            self.add_error("audience_tag", "Choose a tag.")
        if audience in (
            Campaign.Audience.EVENT_INVITEES,
            Campaign.Audience.RESPONSE,
        ) and not cleaned.get("audience_occurrence"):
            self.add_error("audience_occurrence", "Choose an event date.")
        if audience == Campaign.Audience.RESPONSE and not cleaned.get(
            "response_filter"
        ):
            self.add_error("response_filter", "Choose a response status.")
        return cleaned

    def save(self, commit=True):
        campaign = super().save(commit=False)
        campaign.site = self.site
        if commit:
            campaign.full_clean()
            campaign.save()
        return campaign


class CampaignLaunchForm(forms.Form):
    confirm_sms_usage = forms.BooleanField(
        required=False,
        label="I confirm this SMS estimate and available segment usage",
    )


class CampaignTestForm(forms.Form):
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=30, required=False)
    confirm_sms_usage = forms.BooleanField(required=False)

    def __init__(self, *args, campaign, **kwargs):
        self.campaign = campaign
        super().__init__(*args, **kwargs)
        if campaign.channel == Campaign.Channel.EMAIL:
            self.fields["phone"].widget = forms.HiddenInput()
            self.fields["confirm_sms_usage"].widget = forms.HiddenInput()
        else:
            self.fields["email"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        if self.campaign.channel == Campaign.Channel.EMAIL and not cleaned.get("email"):
            self.add_error("email", "Enter a test email address.")
        if self.campaign.channel == Campaign.Channel.SMS:
            if not cleaned.get("phone"):
                self.add_error("phone", "Enter a test phone number.")
            if not cleaned.get("confirm_sms_usage"):
                self.add_error(
                    "confirm_sms_usage", "Confirm the test message's SMS usage."
                )
        return cleaned
