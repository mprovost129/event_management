from django.contrib import admin

from .models import (
    ConnectedAccount,
    ConnectWebhookEvent,
    Dispute,
    FinancialTransition,
    InventoryHold,
    MembershipPayment,
    Order,
    OrderLine,
    Refund,
    Ticket,
    TicketType,
)


@admin.register(ConnectedAccount)
class ConnectedAccountAdmin(admin.ModelAdmin):
    list_display = (
        "site",
        "status",
        "charges_enabled",
        "payouts_enabled",
        "sync_failure_count",
        "permanent_sync_failure_count",
        "last_synced_at",
    )
    list_filter = ("status", "charges_enabled", "payouts_enabled")
    readonly_fields = (
        "stripe_account_id",
        "requirements_due",
        "sync_failure_count",
        "permanent_sync_failure_count",
        "last_sync_attempted_at",
        "last_sync_error",
    )


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    can_delete = False
    readonly_fields = (
        "ticket_type",
        "description",
        "unit_amount_cents",
        "quantity",
        "line_total_cents",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "site",
        "purchaser",
        "total_cents",
        "currency",
        "status",
        "created_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("purchaser__email", "stripe_payment_intent_id")
    inlines = (OrderLineInline,)


for model in (
    TicketType,
    InventoryHold,
    Ticket,
    Refund,
    Dispute,
    FinancialTransition,
    ConnectWebhookEvent,
    MembershipPayment,
):
    admin.site.register(model)
