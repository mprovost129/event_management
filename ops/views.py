from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from communications.models import OutboundMessage, ProviderCallbackEvent
from payments.models import ConnectedAccount, ConnectWebhookEvent, Order
from reviews.forms import ReviewModerationForm
from reviews.models import Review, ReviewModeration
from reviews.services import moderate_review
from sites.models import Site
from sites.reporting import site_summary
from subscriptions.models import PlatformSubscription, StripeWebhookEvent
from users.models import User

from .health import operational_alerts
from .models import AuditEvent, PlatformBrandingSettings, SiteDeletionRequest
from .permissions import platform_admin_required
from .services import (
    active_support_grant,
    approve_site_deletion,
    cancel_site_deletion,
    grant_support_access,
    record_audit_event,
    request_site_deletion,
)


@platform_admin_required
def dashboard(request):
    query = request.GET.get("q", "").strip()
    sites = Site.objects.select_related("platform_subscription").order_by(
        "display_name"
    )
    users = User.objects.order_by("email")
    if query:
        sites = sites.filter(
            Q(display_name__icontains=query) | Q(slug__icontains=query)
        )
        users = users.filter(email__icontains=query)
    stale_before = timezone.now() - timedelta(minutes=15)
    settled_orders = Order.objects.filter(
        status__in=(
            Order.Status.PAID,
            Order.Status.PARTIALLY_REFUNDED,
            Order.Status.REFUNDED,
            Order.Status.DISPUTED,
        )
    )
    fee_totals = settled_orders.aggregate(
        collected=Sum("application_fee_cents"),
        returned=Sum("application_fee_refunded_cents"),
    )
    collected_fee_cents = fee_totals["collected"] or 0
    returned_fee_cents = fee_totals["returned"] or 0
    branding = PlatformBrandingSettings.get_solo()
    context = {
        "query": query,
        "sites": sites[:50],
        "users_found": users[:50],
        "failed_platform_webhooks": StripeWebhookEvent.objects.filter(
            status=StripeWebhookEvent.Status.FAILED
        )[:20],
        "failed_connect_webhooks": ConnectWebhookEvent.objects.filter(
            status=ConnectWebhookEvent.Status.FAILED
        )[:20],
        "failed_callbacks": ProviderCallbackEvent.objects.filter(
            status=ProviderCallbackEvent.Status.FAILED
        )[:20],
        "failed_messages": OutboundMessage.objects.filter(
            status=OutboundMessage.Status.FAILED
        )[:20],
        "stale_messages": OutboundMessage.objects.filter(
            status=OutboundMessage.Status.PROCESSING, updated_at__lte=stale_before
        )[:20],
        "connected_attention": ConnectedAccount.objects.exclude(
            status=ConnectedAccount.Status.READY
        )[:20],
        "reported_reviews": Review.objects.filter(
            moderation_status=Review.ModerationStatus.REPORTED
        )[:20],
        "deletions": SiteDeletionRequest.objects.exclude(
            status=SiteDeletionRequest.Status.COMPLETED
        )[:20],
        "audit_events": AuditEvent.objects.select_related("actor")[:30],
        "operational_alerts": operational_alerts(),
        "platform_fees": {
            "collected": Decimal(collected_fee_cents) / 100,
            "returned": Decimal(returned_fee_cents) / 100,
            "net": Decimal(collected_fee_cents - returned_fee_cents) / 100,
            "orders": settled_orders.count(),
            "sites": settled_orders.values("site_id").distinct().count(),
        },
        "platform_branding": branding,
    }
    return render(request, "ops/dashboard.html", context)


@platform_admin_required
@require_POST
def update_branding(request):
    branding = PlatformBrandingSettings.get_solo()
    show_logo = request.POST.get("show_logo_in_header") == "on"
    show_name = request.POST.get("show_name_in_header") == "on"

    if not show_logo and not show_name:
        messages.error(
            request,
            "Choose at least one platform header branding option: logo or name.",
        )
        return redirect("ops:dashboard")

    branding.show_logo_in_header = show_logo
    branding.show_name_in_header = show_name
    branding.save(
        update_fields=(
            "show_logo_in_header",
            "show_name_in_header",
            "updated_at",
        )
    )
    messages.success(request, "Platform navbar branding updated.")
    return redirect("ops:dashboard")


@platform_admin_required
@require_POST
def support_grant(request, site_id):
    site = get_object_or_404(Site, pk=site_id)
    try:
        grant_support_access(
            site=site,
            actor=request.user,
            reason=request.POST.get("reason", ""),
            hours=int(request.POST.get("hours", 1)),
            request=request,
        )
    except (ValidationError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("ops:dashboard")
    return redirect("ops:support_snapshot", site_id=site.id)


@platform_admin_required
def support_snapshot(request, site_id):
    site = get_object_or_404(Site, pk=site_id)
    grant = active_support_grant(site=site, actor=request.user)
    if grant is None:
        messages.error(request, "Create a current support-access grant first.")
        return redirect("ops:dashboard")
    record_audit_event(
        action="support.site_viewed",
        actor=request.user,
        site_id=site.id,
        target=grant,
        summary={"read_only": True},
        request=request,
    )
    return render(
        request,
        "ops/support_snapshot.html",
        {
            "site": site,
            "grant": grant,
            "summary": site_summary(site),
            "audit_events": AuditEvent.objects.filter(site_id=site.id)[:50],
        },
    )


@platform_admin_required
@require_POST
def suspend_site(request, site_id):
    site = get_object_or_404(
        Site.objects.select_related("platform_subscription"), pk=site_id
    )
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "A suspension reason is required.")
        return redirect("ops:dashboard")
    subscription = site.platform_subscription
    subscription.status = PlatformSubscription.Status.SUSPENDED
    subscription.suspended_at = timezone.now()
    subscription.save(update_fields=("status", "suspended_at", "updated_at"))
    site.status = Site.Status.SUSPENDED
    site.save(update_fields=("status", "updated_at"))
    record_audit_event(
        action="platform.site_suspended",
        actor=request.user,
        site_id=site.id,
        target=subscription,
        summary={"reason": reason[:200]},
        request=request,
    )
    messages.success(request, "Site access suspended.")
    return redirect("ops:dashboard")


@platform_admin_required
@require_POST
def deletion_request(request, site_id):
    site = get_object_or_404(Site, pk=site_id)
    try:
        request_site_deletion(
            site=site,
            actor=request.user,
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "Deletion requested. A different administrator must approve it."
        )
    return redirect("ops:dashboard")


@platform_admin_required
@require_POST
def deletion_approve(request, deletion_id):
    deletion = get_object_or_404(SiteDeletionRequest, pk=deletion_id)
    try:
        approve_site_deletion(deletion=deletion, actor=request.user, request=request)
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "Deletion approved; the retention countdown has started."
        )
    return redirect("ops:dashboard")


@platform_admin_required
@require_POST
def deletion_cancel(request, deletion_id):
    deletion = get_object_or_404(SiteDeletionRequest, pk=deletion_id)
    try:
        cancel_site_deletion(
            deletion=deletion,
            actor=request.user,
            reason=request.POST.get("reason", ""),
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Deletion request canceled.")
    return redirect("ops:dashboard")


@platform_admin_required
@require_POST
def moderate(request, review_id, action):
    review = get_object_or_404(Review, pk=review_id)
    form = ReviewModerationForm(request.POST)
    if form.is_valid() and action in ReviewModeration.Action.values:
        moderate_review(
            review=review,
            actor=request.user,
            action=action,
            reason=form.cleaned_data["reason"],
            request=request,
        )
        messages.success(request, "Review moderation recorded.")
    else:
        messages.error(request, "A valid moderation action and reason are required.")
    return redirect("ops:dashboard")
