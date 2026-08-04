import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from contacts.models import MembershipPlan, MemberSubscription
from core.rate_limits import public_write_rate_limit
from events.models import EventOccurrence
from events.services import public_occurrence_url
from ops.services import record_audit_event
from sites.permissions import (
    site_staff_required,
    subscriber_admin_required,
    subscriber_recovery_required,
)

from .forms import (
    MembershipJoinForm,
    MembershipPlanForm,
    RefundForm,
    TicketCheckoutForm,
    TicketTypeForm,
)
from .gateway import CommerceNotConfigured, create_onboarding_link
from .models import (
    ConnectedAccount,
    ConnectWebhookEvent,
    Dispute,
    Order,
    TicketType,
)
from .services import (
    CommerceUnavailable,
    InventoryUnavailable,
    attach_checkout_session,
    attach_member_checkout,
    commerce_summary,
    occurrence_for_expired_checkout_token,
    prepare_refund,
    process_connect_event,
    refresh_connected_account,
    registration_for_checkout_token,
    release_expired_holds,
    require_commerce_ready,
    reserve_ticket_order,
    start_connected_account,
    start_member_subscription,
    submit_refund,
    ticket_inventory,
    ticket_inventory_map,
)

logger = logging.getLogger(__name__)


def _public_site(request):
    site = getattr(request, "site", None)
    if site is None or not site.accepts_public_traffic or not site.is_published:
        raise Http404("Site not found.")
    return site


def _money(cents):
    return Decimal(cents) / 100


def _ticket_application_fee_percent():
    return Decimal(settings.TICKET_APPLICATION_FEE_BPS) / 100


@site_staff_required
def manage(request, site_id):
    site = request.authorized_site
    connected = ConnectedAccount.objects.filter(site=site).first()

    if connected and request.GET.get("connect") == "returned":
        try:
            connected = refresh_connected_account(connected)
        except (CommerceNotConfigured, stripe.StripeError):
            messages.warning(
                request,
                "We could not confirm your Stripe status just now. "
                "Try Refresh status in a moment.",
            )
        else:
            if connected.commerce_ready:
                messages.success(
                    request,
                    "Stripe setup is complete. You can start selling tickets.",
                )
            else:
                messages.info(
                    request,
                    "Stripe still needs a few details before you can accept payments.",
                )
        return redirect("payments:manage", site_id=site.id)

    ticket_types = list(
        TicketType.objects.for_site(site)
        .select_related("occurrence__event")
        .order_by("occurrence__starts_at", "name")
    )
    inventory_by_type = ticket_inventory_map(ticket_types)
    for ticket_type in ticket_types:
        ticket_type.inventory = inventory_by_type[ticket_type.id]
        ticket_type.price_display = _money(ticket_type.amount_cents)
    orders = Order.objects.for_site(site).select_related(
        "purchaser", "occurrence__event"
    )[:25]
    for order in orders:
        order.total_display = _money(order.total_cents)
        order.refunded_display = _money(order.refunded_cents)
        order.application_fee_display = _money(order.application_fee_cents)
    plans = MembershipPlan.objects.for_site(site)
    for plan in plans:
        plan.price_display = _money(plan.amount_cents)
    member_subscriptions = MemberSubscription.objects.for_site(site).select_related(
        "member__contact", "plan"
    )[:25]
    disputes = Dispute.objects.for_site(site).select_related(
        "order__purchaser", "order__occurrence__event"
    )[:25]
    failed_webhooks = (
        ConnectWebhookEvent.objects.filter(
            connected_account_id=connected.stripe_account_id,
            status=ConnectWebhookEvent.Status.FAILED,
        ).count()
        if connected
        else 0
    )
    summary = commerce_summary(site)
    summary = {
        key.replace("_cents", ""): _money(value) if key.endswith("_cents") else value
        for key, value in summary.items()
    }
    return render(
        request,
        "payments/manage.html",
        {
            "site": site,
            "site_role": request.site_role,
            "connected": connected,
            "ticket_types": ticket_types,
            "orders": orders,
            "plans": plans,
            "member_subscriptions": member_subscriptions,
            "disputes": disputes,
            "failed_webhooks": failed_webhooks,
            "summary": summary,
            "ticket_application_fee_percent": _ticket_application_fee_percent(),
        },
    )


def _account_link(request, connected):
    manage_url = request.build_absolute_uri(
        reverse("payments:manage", kwargs={"site_id": connected.site_id})
    )
    refresh_url = request.build_absolute_uri(
        reverse("payments:connect_refresh", kwargs={"site_id": connected.site_id})
    )
    return create_onboarding_link(
        account_id=connected.stripe_account_id,
        refresh_url=refresh_url,
        return_url=manage_url + "?connect=returned",
    )


@require_POST
@subscriber_admin_required
def connect_start(request, site_id):
    try:
        connected = start_connected_account(site=request.authorized_site)
        link = _account_link(request, connected)
    except (CommerceUnavailable, CommerceNotConfigured, stripe.StripeError):
        logger.exception("Connect onboarding failed for site %s", site_id)
        messages.error(
            request,
            "We could not reach Stripe just now. Please try again in a minute.",
        )
        return redirect("payments:manage", site_id=site_id)
    return redirect(link.url)


@subscriber_admin_required
def connect_refresh(request, site_id):
    connected = get_object_or_404(ConnectedAccount, site=request.authorized_site)
    try:
        link = _account_link(request, connected)
    except (CommerceNotConfigured, stripe.StripeError):
        logger.exception("Connect onboarding resume failed for site %s", site_id)
        messages.error(
            request,
            "We could not reach Stripe just now. Please try again in a minute.",
        )
        return redirect("payments:manage", site_id=site_id)
    return redirect(link.url)


@require_POST
@subscriber_admin_required
def connect_sync(request, site_id):
    connected = get_object_or_404(ConnectedAccount, site=request.authorized_site)
    try:
        connected = refresh_connected_account(connected)
    except (CommerceNotConfigured, stripe.StripeError):
        logger.exception("Connect status sync failed for site %s", site_id)
        messages.error(
            request,
            "We could not reach Stripe just now. Please try again in a minute.",
        )
    else:
        messages.success(
            request, f"Stripe status refreshed: {connected.get_status_display()}."
        )
    return redirect("payments:manage", site_id=site_id)


@site_staff_required
@require_http_methods(["GET", "POST"])
def ticket_type_create(request, site_id, occurrence_id):
    site = request.authorized_site
    occurrence = get_object_or_404(
        EventOccurrence.objects.for_site(site).select_related("event"), pk=occurrence_id
    )
    form = TicketTypeForm(request.POST or None, site=site, occurrence=occurrence)
    connected = ConnectedAccount.objects.filter(site=site).first()
    if request.method == "POST" and form.is_valid():
        try:
            require_commerce_ready(site)
            ticket_type = form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            record_audit_event(
                action="commerce.ticket_type.created",
                actor=request.user,
                site_id=site.id,
                target=ticket_type,
                summary={
                    "amount_cents": ticket_type.amount_cents,
                    "quantity": ticket_type.quantity,
                },
                request=request,
            )
            messages.success(
                request,
                "Ticket type created. New going responses will require payment.",
            )
            return redirect("payments:manage", site_id=site.id)
    return render(
        request,
        "payments/ticket_type_form.html",
        {
            "site": site,
            "occurrence": occurrence,
            "form": form,
            "connected": connected,
            "ticket_application_fee_percent": _ticket_application_fee_percent(),
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def ticket_type_edit(request, site_id, ticket_type_id):
    site = request.authorized_site
    ticket_type = get_object_or_404(
        TicketType.objects.for_site(site).select_related("occurrence__event"),
        pk=ticket_type_id,
    )
    form = TicketTypeForm(
        request.POST or None,
        instance=ticket_type,
        site=site,
        occurrence=ticket_type.occurrence,
    )
    connected = ConnectedAccount.objects.filter(site=site).first()
    if request.method == "POST" and form.is_valid():
        inventory = ticket_inventory(ticket_type)
        committed = inventory["sold"] + inventory["held"]
        if form.cleaned_data["quantity"] < committed:
            form.add_error(
                "quantity",
                f"Quantity cannot be lower than {committed} sold or currently held tickets.",
            )
        else:
            form.save()
            messages.success(request, "Ticket type updated.")
            return redirect("payments:manage", site_id=site.id)
    return render(
        request,
        "payments/ticket_type_form.html",
        {
            "site": site,
            "occurrence": ticket_type.occurrence,
            "ticket_type": ticket_type,
            "form": form,
            "connected": connected,
            "inventory": ticket_inventory(ticket_type),
            "ticket_application_fee_percent": _ticket_application_fee_percent(),
        },
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("ticket-checkout")
def ticket_checkout(request, token):
    site = _public_site(request)
    registration = registration_for_checkout_token(site=site, token=token)
    if registration is None:
        occurrence = occurrence_for_expired_checkout_token(site=site, token=token)
        return render(
            request,
            "payments/ticket_checkout_expired.html",
            {
                "site": site,
                "event_url": public_occurrence_url(occurrence) if occurrence else "",
            },
            status=404,
        )
    participant_count = registration.participants.filter(status="active").count()
    form = TicketCheckoutForm(
        request.POST or None,
        occurrence=registration.occurrence,
        participant_count=participant_count,
    )
    ticket_options = []
    available_ids = []
    for ticket_type in form.fields["ticket_type"].queryset:
        inventory = ticket_inventory(ticket_type)
        if inventory["remaining"] >= participant_count:
            ticket_type.inventory = inventory
            ticket_type.price_display = _money(ticket_type.amount_cents)
            ticket_type.total_display = _money(
                ticket_type.amount_cents * participant_count
            )
            available_ids.append(ticket_type.id)
            ticket_options.append(ticket_type)
    form.fields["ticket_type"].queryset = form.fields["ticket_type"].queryset.filter(
        id__in=available_ids
    )
    if request.method == "POST" and form.is_valid():
        try:
            release_expired_holds()
            order, line = reserve_ticket_order(
                registration=registration,
                ticket_type=form.cleaned_data["ticket_type"],
            )
            occurrence_url = request.build_absolute_uri(
                reverse(
                    "events:occurrence_detail",
                    kwargs={
                        "slug": registration.occurrence.event.slug,
                        "occurrence_id": registration.occurrence_id,
                    },
                )
            )
            session = attach_checkout_session(
                order=order,
                line=line,
                success_url=occurrence_url + "?checkout=success",
                cancel_url=occurrence_url + "?checkout=canceled",
            )
        except (
            CommerceUnavailable,
            InventoryUnavailable,
            CommerceNotConfigured,
        ) as exc:
            form.add_error(None, exc)
        except stripe.StripeError:
            form.add_error(
                None, "Stripe Checkout is temporarily unavailable. Please try again."
            )
        else:
            return redirect(session.url)
    return render(
        request,
        "payments/ticket_checkout.html",
        {
            "site": site,
            "registration": registration,
            "participant_count": participant_count,
            "form": form,
            "ticket_options": ticket_options,
        },
    )


@subscriber_recovery_required
@require_http_methods(["GET", "POST"])
def refund_order(request, site_id, order_id):
    site = request.authorized_site
    order = get_object_or_404(
        Order.objects.for_site(site).select_related("purchaser", "occurrence__event"),
        pk=order_id,
    )
    form = RefundForm(request.POST or None, order=order)
    if request.method == "POST" and form.is_valid():
        refund = prepare_refund(
            order=order,
            amount_cents=int(form.cleaned_data["amount"] * 100),
            reason=form.cleaned_data["reason"],
            actor=request.user,
        )
        try:
            submit_refund(refund)
        except (CommerceNotConfigured, stripe.StripeError):
            logger.exception("Refund submission failed for order %s", order_id)
            messages.error(
                request,
                "We could not reach Stripe just now. Please try again in a minute.",
            )
        else:
            record_audit_event(
                action="commerce.refund.requested",
                actor=request.user,
                site_id=site.id,
                target=refund,
                summary={
                    "order_id": str(order.id),
                    "amount_cents": refund.amount_cents,
                },
                request=request,
            )
            messages.success(
                request,
                "Refund submitted. Stripe will confirm its final status by webhook.",
            )
            return redirect("payments:manage", site_id=site.id)
    refund_history = list(order.refunds.order_by("-created_at"))
    for refund in refund_history:
        refund.amount_display = _money(refund.amount_cents)
    return render(
        request,
        "payments/refund_form.html",
        {
            "site": site,
            "order": order,
            "form": form,
            "total": _money(order.total_cents),
            "refund_history": refund_history,
        },
    )


@subscriber_admin_required
@require_http_methods(["GET", "POST"])
def membership_plan_create(request, site_id):
    site = request.authorized_site
    form = MembershipPlanForm(request.POST or None, site=site)
    connected = ConnectedAccount.objects.filter(site=site).first()
    if request.method == "POST" and form.is_valid():
        try:
            require_commerce_ready(site)
            plan = form.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            record_audit_event(
                action="commerce.membership_plan.created",
                actor=request.user,
                site_id=site.id,
                target=plan,
                summary={"amount_cents": plan.amount_cents, "interval": plan.interval},
                request=request,
            )
            messages.success(request, "Membership plan created.")
            return redirect("payments:manage", site_id=site.id)
    return render(
        request,
        "payments/membership_plan_form.html",
        {"site": site, "form": form, "connected": connected},
    )


@subscriber_admin_required
@require_http_methods(["GET", "POST"])
def membership_plan_edit(request, site_id, plan_id):
    site = request.authorized_site
    plan = get_object_or_404(MembershipPlan.objects.for_site(site), pk=plan_id)
    form = MembershipPlanForm(request.POST or None, instance=plan, site=site)
    connected = ConnectedAccount.objects.filter(site=site).first()
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Membership plan updated.")
        return redirect("payments:manage", site_id=site.id)
    return render(
        request,
        "payments/membership_plan_form.html",
        {"site": site, "plan": plan, "form": form, "connected": connected},
    )


def membership_plans(request):
    site = _public_site(request)
    plans = MembershipPlan.objects.for_site(site).filter(is_active=True)
    connected = ConnectedAccount.objects.filter(site=site).first()
    if connected is None or not connected.commerce_ready:
        plans = plans.none()
    for plan in plans:
        plan.price_display = _money(plan.amount_cents)
    return render(
        request, "public/membership_plans.html", {"site": site, "plans": plans}
    )


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("membership-checkout")
def membership_join(request, plan_id):
    site = _public_site(request)
    plan = get_object_or_404(
        MembershipPlan.objects.for_site(site), pk=plan_id, is_active=True
    )
    form = MembershipJoinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            connected = require_commerce_ready(site)
            member_subscription = start_member_subscription(
                site=site,
                plan=plan,
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                account_id=connected.stripe_account_id,
            )
            plans_url = request.build_absolute_uri(reverse("payments:membership_plans"))
            session = attach_member_checkout(
                member_subscription=member_subscription,
                success_url=plans_url + "?membership=success",
                cancel_url=plans_url + "?membership=canceled",
            )
        except (CommerceUnavailable, CommerceNotConfigured) as exc:
            form.add_error(None, exc)
        except stripe.StripeError:
            form.add_error(
                None, "Stripe Checkout is temporarily unavailable. Please try again."
            )
        else:
            return redirect(session.url)
    return render(
        request,
        "payments/membership_join.html",
        {"site": site, "plan": plan, "price": _money(plan.amount_cents), "form": form},
    )


@csrf_exempt
@require_POST
def connect_webhook(request):
    if not settings.STRIPE_CONNECT_WEBHOOK_SECRET:
        return HttpResponse("Stripe Connect webhook is not configured.", status=503)
    try:
        event = stripe.Webhook.construct_event(
            payload=request.body,
            sig_header=request.headers.get("Stripe-Signature", ""),
            secret=settings.STRIPE_CONNECT_WEBHOOK_SECRET,
        )
        process_connect_event(event)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest("Invalid webhook.")
    return HttpResponse(status=200)
