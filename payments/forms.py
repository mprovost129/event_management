from decimal import Decimal, InvalidOperation

from django import forms
from django.db.models import Q
from django.utils import timezone

from contacts.models import MembershipPlan
from events.models import Registration

from .models import TicketType


class TicketTypeForm(forms.ModelForm):
    price = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.50")
    )

    class Meta:
        model = TicketType
        fields = (
            "name",
            "description",
            "quantity",
            "max_per_order",
            "sales_start_at",
            "sales_end_at",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "sales_start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "sales_end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, site, occurrence, **kwargs):
        self.site = site
        self.occurrence = occurrence
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["price"].initial = Decimal(self.instance.amount_cents) / 100

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.site = self.site
        instance.occurrence = self.occurrence
        instance.currency = self.site.currency
        instance.amount_cents = int(self.cleaned_data["price"] * 100)
        if commit:
            instance.full_clean()
            instance.save()
        return instance

    def clean(self):
        cleaned_data = super().clean()
        confirmed = self.occurrence.registrations.filter(
            response=Registration.Response.GOING,
            payment_status__in=(
                Registration.PaymentStatus.NOT_REQUIRED,
                Registration.PaymentStatus.PAID,
            ),
        )
        if confirmed.exists() and not self.instance.pk:
            raise forms.ValidationError(
                "Paid tickets cannot be enabled after confirmed going responses exist."
            )
        return cleaned_data


class TicketCheckoutForm(forms.Form):
    ticket_type = forms.ModelChoiceField(queryset=TicketType.objects.none())

    def __init__(self, *args, occurrence, participant_count, **kwargs):
        self.occurrence = occurrence
        self.participant_count = participant_count
        super().__init__(*args, **kwargs)
        now = timezone.now()
        self.fields["ticket_type"].queryset = TicketType.objects.filter(
            occurrence=occurrence,
            is_active=True,
        ).filter(
            Q(sales_start_at__isnull=True) | Q(sales_start_at__lte=now),
            Q(sales_end_at__isnull=True) | Q(sales_end_at__gt=now),
        )

    def clean_ticket_type(self):
        ticket_type = self.cleaned_data["ticket_type"]
        if self.participant_count > ticket_type.max_per_order:
            raise forms.ValidationError(
                "This ticket type does not allow that many participants per order."
            )
        return ticket_type


class RefundForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.01")
    )
    reason = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, order, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        remaining = Decimal(order.total_cents - order.refunded_cents) / 100
        self.fields["amount"].initial = remaining
        self.fields[
            "amount"
        ].help_text = f"Up to {remaining:.2f} {order.currency.upper()}"

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        try:
            amount_cents = int(amount * 100)
        except (InvalidOperation, ValueError):
            raise forms.ValidationError("Enter a valid refund amount.") from None
        if amount_cents > self.order.total_cents - self.order.refunded_cents:
            raise forms.ValidationError("The refund exceeds the remaining order total.")
        return amount


class MembershipPlanForm(forms.ModelForm):
    price = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0.50")
    )

    class Meta:
        model = MembershipPlan
        fields = ("name", "description", "interval", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["price"].initial = Decimal(self.instance.amount_cents) / 100
            if self.instance.stripe_price_id:
                self.fields["price"].disabled = True
                self.fields["interval"].disabled = True

    def save(self, commit=True):
        plan = super().save(commit=False)
        plan.site = self.site
        plan.currency = self.site.currency
        plan.amount_cents = int(self.cleaned_data["price"] * 100)
        if commit:
            plan.full_clean()
            plan.save()
        return plan


class MembershipJoinForm(forms.Form):
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    email = forms.EmailField()

    def clean_email(self):
        return self.cleaned_data["email"].strip().casefold()
