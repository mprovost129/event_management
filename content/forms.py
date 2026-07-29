from django import forms

from sites.models import Site

from .images import prepare_image
from .models import BlogPost, PublishingStatus, SitePage


class PublishingFormMixin:
    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get(
            "status"
        ) == PublishingStatus.SCHEDULED and not cleaned_data.get("publish_at"):
            self.add_error(
                "publish_at", "Choose a publication time for scheduled content."
            )
        return cleaned_data


class SitePageForm(PublishingFormMixin, forms.ModelForm):
    class Meta:
        model = SitePage
        fields = (
            "title",
            "navigation_label",
            "body",
            "status",
            "publish_at",
            "meta_title",
            "meta_description",
        )
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 12,
                    "placeholder": "Tell visitors what they should know about your group.",
                }
            ),
            "publish_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }


class BlogPostForm(PublishingFormMixin, forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = (
            "title",
            "slug",
            "excerpt",
            "body",
            "featured_image",
            "author_display_name",
            "status",
            "publish_at",
            "meta_description",
        )
        widgets = {
            "title": forms.TextInput(
                attrs={"placeholder": "Example: What to know before Friday's dance"}
            ),
            "slug": forms.TextInput(attrs={"placeholder": "friday-dance-details"}),
            "excerpt": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "A short summary for the blog list and homepage.",
                }
            ),
            "body": forms.Textarea(
                attrs={
                    "rows": 16,
                    "placeholder": "Write the full update here...",
                }
            ),
            "featured_image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "publish_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        self.fields["slug"].help_text = (
            "Used in the post's web address. Lowercase letters, numbers, and hyphens only."
        )
        self.fields["excerpt"].help_text = (
            "Aim for one or two sentences that make people want to read more."
        )
        self.fields["author_display_name"].label = "Public author name"
        self.fields["author_display_name"].help_text = (
            "Optional. Use the group name if the post should not show a personal name."
        )

    def clean_slug(self):
        slug = self.cleaned_data["slug"].lower()
        existing = BlogPost.objects.for_site(self.site).filter(slug=slug)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("That blog URL is already in use.")
        return slug

    def clean_featured_image(self):
        return prepare_image(
            self.cleaned_data.get("featured_image"), max_dimension=1800
        )


class SitePresentationForm(forms.Form):
    display_name = forms.CharField(
        max_length=160,
        label="Group or brand name",
        help_text="This appears in the website header and browser title.",
    )
    template_key = forms.ChoiceField(
        choices=Site.Template.choices, widget=forms.RadioSelect
    )
    is_published = forms.BooleanField(
        required=False,
        help_text="Make the public website available on its Gather HQs subdomain.",
    )
    logo = forms.FileField(
        required=False,
        help_text="A square or wide PNG, JPG, or WebP works best.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )
    hero_image = forms.FileField(
        required=False,
        help_text="Choose a wide image with room for readable text.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )
    hero_heading = forms.CharField(
        max_length=180,
        required=False,
        help_text="The first message visitors see. Your group name is used if left blank.",
    )
    hero_text = forms.CharField(
        max_length=320, required=False, widget=forms.Textarea(attrs={"rows": 3})
    )
    primary_color = forms.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        max_length=7,
        help_text="Used for links, buttons, and highlights.",
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    secondary_color = forms.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        max_length=7,
        help_text="Used for supporting text and accents.",
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    typography_key = forms.ChoiceField(
        choices=(
            ("system", "Clean system type"),
            ("serif", "Friendly serif"),
            ("rounded", "Rounded sans serif"),
        )
    )

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        theme = site.theme
        if not self.is_bound:
            self.initial.update(
                {
                    "display_name": site.display_name,
                    "template_key": site.template_key,
                    "is_published": site.is_published,
                    "hero_heading": theme.hero_heading,
                    "hero_text": theme.hero_text,
                    "primary_color": theme.primary_color,
                    "secondary_color": theme.secondary_color,
                    "typography_key": theme.typography_key,
                }
            )

    def save(self):
        site = self.site
        site.display_name = self.cleaned_data["display_name"]
        site.template_key = self.cleaned_data["template_key"]
        site.is_published = self.cleaned_data["is_published"]
        site.save(
            update_fields=("display_name", "template_key", "is_published", "updated_at")
        )
        theme = site.theme
        for field in (
            "hero_heading",
            "hero_text",
            "primary_color",
            "secondary_color",
            "typography_key",
        ):
            setattr(theme, field, self.cleaned_data[field])
        if self.cleaned_data.get("logo"):
            theme.logo = self.cleaned_data["logo"]
        if self.cleaned_data.get("hero_image"):
            theme.hero_image = self.cleaned_data["hero_image"]
        theme.save()
        return site

    def clean_logo(self):
        return prepare_image(self.cleaned_data.get("logo"), max_dimension=800)

    def clean_hero_image(self):
        return prepare_image(self.cleaned_data.get("hero_image"), max_dimension=2400)


class NewsletterSignupForm(forms.Form):
    first_name = forms.CharField(max_length=100, required=False)
    last_name = forms.CharField(max_length=100, required=False)
    email = forms.EmailField()
    consent = forms.BooleanField(
        label="I agree to receive email updates from this group."
    )
