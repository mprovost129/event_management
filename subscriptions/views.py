import stripe
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from sites.permissions import subscriber_admin_required

from .gateway import (
    BillingNotConfigured,
    create_checkout_session,
    create_portal_session,
)
from .services import process_stripe_event


@require_POST
@subscriber_admin_required
def checkout(request, site_id):
    subscription = request.authorized_site.platform_subscription
    try:
        session = create_checkout_session(
            subscription=subscription,
            owner=request.user,
            success_url=request.build_absolute_uri(
                reverse("sites:dashboard", kwargs={"site_id": site_id})
            )
            + "?billing=success",
            cancel_url=request.build_absolute_uri(
                reverse("sites:dashboard", kwargs={"site_id": site_id})
            )
            + "?billing=canceled",
        )
    except BillingNotConfigured as exc:
        messages.error(request, str(exc))
        return redirect("sites:dashboard", site_id=site_id)
    return redirect(session.url)


@require_POST
@subscriber_admin_required
def portal(request, site_id):
    subscription = request.authorized_site.platform_subscription
    try:
        session = create_portal_session(
            subscription=subscription,
            return_url=request.build_absolute_uri(
                reverse("sites:dashboard", kwargs={"site_id": site_id})
            ),
        )
    except BillingNotConfigured as exc:
        messages.error(request, str(exc))
        return redirect("sites:dashboard", site_id=site_id)
    return redirect(session.url)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse("Stripe webhook is not configured.", status=503)
    try:
        event = stripe.Webhook.construct_event(
            payload=request.body,
            sig_header=request.headers.get("Stripe-Signature", ""),
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
        process_stripe_event(event)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponseBadRequest("Invalid webhook.")
    return HttpResponse(status=200)
