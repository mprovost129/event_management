from decimal import Decimal, InvalidOperation

from django import forms
from django.db.models import Q
from django.utils import timezone

from contacts.models import MembershipPlan
from events.models import Registration

from .models import TicketType


class TicketTypeForm(forms.ModelForm):
    price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.50"),
        label="Price per person",
        help_text="Every named participant, including each guest, needs one ticket.",
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
            "refund_policy",
            "is_active",
        )
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional details such as what admission includes.",
                }
            ),
            "sales_start_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "sales_end_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "refund_policy": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Example: Full refunds up to 48 hours before the event. "
                        "No refunds after that, but tickets can be transferred."
                    ),
                }
            ),
        }

    def __init__(self, *args, site, occurrence, **kwargs):
        self.site = site
        self.occurrence = occurrence
        super().__init__(*args, **kwargs)
        if not self.instance._state.adding:
            self.fields["price"].initial = Decimal(self.instance.amount_cents) / 100
        self.fields[
            "name"
        ].help_text = "Examples: General admission, Early bird, or Member ticket."
        self.fields["quantity"].label = "Tickets available"
        self.fields[
            "quantity"
        ].help_text = "This inventory is tracked separately for this event date."
        self.fields["max_per_order"].label = "Maximum tickets per RSVP"
        self.fields[
            "max_per_order"
        ].help_text = "Must be large enough for the attendee plus their allowed guests."
        self.fields["sales_start_at"].label = "Sales open"
        self.fields["sales_end_at"].label = "Sales close"
        self.fields[
            "is_active"
        ].help_text = "Inactive tickets are hidden from new checkout sessions."
        self.fields["refund_policy"].label = "Refund policy"
        # A buyer has to be told the terms before paying. If the organization
        # has no default, this ticket type has to carry one.
        if not site.default_refund_policy.strip():
            self.fields["refund_policy"].required = True
            self.fields["refund_policy"].help_text = (
                "Required, because your organization has not set a default "
                "refund policy yet. Buyers see this before they pay."
            )

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
        sales_start = cleaned_data.get("sales_start_at")
        sales_end = cleaned_data.get("sales_end_at")
        if sales_start and sales_end and sales_end <= sales_start:
            self.add_error("sales_end_at", "Sales must close after they open.")
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


class TicketCheckoutChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, ticket_type):
        price = Decimal(ticket_type.amount_cents) / 100
        return f"{ticket_type.name} - ${price:.2f} {ticket_type.currency.upper()} per person"


class TicketCheckoutForm(forms.Form):
    ticket_type = TicketCheckoutChoiceField(
        queryset=TicketType.objects.none(),
        widget=forms.RadioSelect,
        label="Ticket option",
    )

    def __init__(self, *args, occurrence, participant_count, **kwargs):
        self.occurrence = occurrence
        self.participant_count = participant_count
        super().__init__(*args, **kwargs)
        now = timezone.now()
        self.fields["ticket_type"].queryset = (
            TicketType.objects.select_related("site").filter(
                occurrence=occurrence,
                is_active=True,
                max_per_order__gte=participant_count,
            )
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
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.50"),
        label="Dues amount",
    )

    class Meta:
        model = MembershipPlan
        fields = ("name", "description", "interval", "is_active")
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Explain what membership supports or includes.",
                }
            ),
            "interval": forms.RadioSelect,
        }

    def __init__(self, *args, site, **kwargs):
        self.site = site
        super().__init__(*args, **kwargs)
        self.fields[
            "name"
        ].help_text = (
            "Examples: Supporting member, Annual club member, or Dance family."
        )
        self.fields[
            "is_active"
        ].help_text = (
            "Inactive plans are hidden from new members but keep their history."
        )
        if not self.instance._state.adding:
            self.fields["price"].initial = Decimal(self.instance.amount_cents) / 100
            if self.instance.stripe_price_id:
                self.fields["price"].disabled = True
                self.fields["interval"].disabled = True
                self.fields[
                    "price"
                ].help_text = "Price is locked after Stripe creates the recurring plan."
                self.fields[
                    "interval"
                ].help_text = (
                    "Billing frequency is locked after Stripe creates the plan."
                )

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
