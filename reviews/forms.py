from django import forms

from .models import Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {
            "rating": forms.Select(
                choices=tuple(
                    (value, f"{value} star{'s' if value != 1 else ''}")
                    for value in range(1, 6)
                )
            ),
            "comment": forms.Textarea(attrs={"rows": 5}),
        }


class ReviewResponseForm(forms.Form):
    response = forms.CharField(
        max_length=3000, widget=forms.Textarea(attrs={"rows": 5})
    )


class ReviewReportForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class ReviewModerationForm(forms.Form):
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
