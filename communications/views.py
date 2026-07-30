import hashlib
import hmac
import json

from django.conf import settings
from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from content.models import BlogPost
from core.pagination import paginate
from ops.services import record_audit_event
from sites.permissions import site_staff_required

from .callbacks import process_provider_callback
from .campaigns import (
    CampaignUnavailable,
    SmsLimitExceeded,
    campaign_metrics,
    campaign_preview,
    duplicate_campaign,
    launch_campaign,
    queue_campaign_test,
    unsubscribe,
)
from .forms import CampaignForm, CampaignLaunchForm, CampaignTestForm
from .models import Campaign
from .resend_webhooks import process_resend_webhook


@site_staff_required
def campaign_list(request, site_id):
    site = request.authorized_site
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "all")
    channel = request.GET.get("channel", "all")
    campaigns_qs = (
        Campaign.objects.for_site(site)
        .select_related("created_by")
        .annotate(
            sent_metric=Count(
                "recipients",
                filter=Q(recipients__sent_at__isnull=False),
                distinct=True,
            ),
            delivered_metric=Count(
                "recipients",
                filter=Q(recipients__delivered_at__isnull=False),
                distinct=True,
            ),
            failed_metric=Count(
                "recipients",
                filter=Q(recipients__status="failed"),
                distinct=True,
            ),
        )
    )
    if status in Campaign.Status.values:
        campaigns_qs = campaigns_qs.filter(status=status)
    else:
        status = "all"
    if channel in Campaign.Channel.values:
        campaigns_qs = campaigns_qs.filter(channel=channel)
    else:
        channel = "all"
    if query:
        campaigns_qs = campaigns_qs.filter(
            Q(name__icontains=query)
            | Q(subject__icontains=query)
            | Q(body__icontains=query)
        )
    campaigns = paginate(
        request,
        campaigns_qs.order_by("-created_at", "id"),
    )
    for campaign in campaigns:
        campaign.metrics = {
            "sent": campaign.sent_metric,
            "delivered": campaign.delivered_metric,
            "failed": campaign.failed_metric,
        }
    return render(
        request,
        "communications/campaign_list.html",
        {
            "site": site,
            "campaigns": campaigns,
            "query": query,
            "selected_status": status,
            "selected_channel": channel,
            "status_choices": Campaign.Status.choices,
            "channel_choices": Campaign.Channel.choices,
            "page_obj": campaigns,
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def campaign_create(request, site_id):
    site = request.authorized_site
    initial = {}
    source_post = None
    source_post_id = request.GET.get("blog_post") or request.POST.get(
        "source_blog_post"
    )
    if source_post_id:
        source_post = get_object_or_404(
            BlogPost.objects.for_site(site), pk=source_post_id
        )
        initial = {
            "name": f"Newsletter: {source_post.title}"[:160],
            "subject": source_post.title,
            "body": source_post.body,
            "channel": Campaign.Channel.EMAIL,
        }
    form = CampaignForm(request.POST or None, site=site, initial=initial)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.created_by = request.user
        if request.POST.get("source_blog_post"):
            campaign.source_blog_post = get_object_or_404(
                BlogPost.objects.for_site(site), pk=request.POST["source_blog_post"]
            )
        campaign.full_clean()
        campaign.save()
        record_audit_event(
            action="campaign.created",
            actor=request.user,
            site_id=site.id,
            target=campaign,
            summary={"channel": campaign.channel, "audience": campaign.audience},
            request=request,
        )
        messages.success(
            request, "Campaign draft created. Review its audience before sending."
        )
        return redirect(
            "communications:campaign_preview", site_id=site.id, campaign_id=campaign.id
        )
    return render(
        request,
        "communications/campaign_form.html",
        {"site": site, "form": form, "source_post": source_post},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def campaign_edit(request, site_id, campaign_id):
    site = request.authorized_site
    campaign = get_object_or_404(Campaign.objects.for_site(site), pk=campaign_id)
    if campaign.status != Campaign.Status.DRAFT:
        messages.error(request, "Only draft campaigns can be edited.")
        return redirect(
            "communications:campaign_preview", site_id=site.id, campaign_id=campaign.id
        )
    form = CampaignForm(request.POST or None, instance=campaign, site=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Campaign draft saved.")
        return redirect(
            "communications:campaign_preview", site_id=site.id, campaign_id=campaign.id
        )
    return render(
        request,
        "communications/campaign_form.html",
        {
            "site": site,
            "campaign": campaign,
            "form": form,
            "source_post": campaign.source_blog_post,
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def campaign_preview_view(request, site_id, campaign_id):
    site = request.authorized_site
    campaign = get_object_or_404(Campaign.objects.for_site(site), pk=campaign_id)
    preview = campaign_preview(campaign)
    launch_form = CampaignLaunchForm(prefix="launch")
    test_form = CampaignTestForm(prefix="test", campaign=campaign)
    if request.method == "POST" and request.POST.get("action") == "launch":
        launch_form = CampaignLaunchForm(request.POST, prefix="launch")
        if launch_form.is_valid():
            try:
                launch_campaign(
                    campaign=campaign,
                    actor=request.user,
                    usage_confirmed=launch_form.cleaned_data["confirm_sms_usage"],
                )
            except (CampaignUnavailable, SmsLimitExceeded) as exc:
                launch_form.add_error(None, exc)
            else:
                record_audit_event(
                    action="campaign.launched",
                    actor=request.user,
                    site_id=site.id,
                    target=campaign,
                    summary={
                        "eligible": preview["eligible_count"],
                        "estimated_segments": preview["estimated_segments"],
                    },
                    request=request,
                )
                messages.success(
                    request, "Campaign was queued for background delivery."
                )
                return redirect(
                    "communications:campaign_preview",
                    site_id=site.id,
                    campaign_id=campaign.id,
                )
    elif request.method == "POST" and request.POST.get("action") == "test":
        test_form = CampaignTestForm(request.POST, prefix="test", campaign=campaign)
        if test_form.is_valid():
            try:
                queue_campaign_test(
                    campaign=campaign,
                    email=test_form.cleaned_data.get("email", ""),
                    phone=test_form.cleaned_data.get("phone", ""),
                    confirm_sms_usage=test_form.cleaned_data.get(
                        "confirm_sms_usage", False
                    ),
                )
            except (CampaignUnavailable, SmsLimitExceeded) as exc:
                test_form.add_error(None, exc)
            else:
                messages.success(request, "Test message queued.")
                return redirect(
                    "communications:campaign_preview",
                    site_id=site.id,
                    campaign_id=campaign.id,
                )
    campaign.refresh_from_db()
    return render(
        request,
        "communications/campaign_preview.html",
        {
            "site": site,
            "campaign": campaign,
            "preview": preview,
            "metrics": campaign_metrics(campaign),
            "launch_form": launch_form,
            "test_form": test_form,
        },
    )


@require_POST
@site_staff_required
def campaign_duplicate(request, site_id, campaign_id):
    source = get_object_or_404(
        Campaign.objects.for_site(request.authorized_site), pk=campaign_id
    )
    campaign = duplicate_campaign(campaign=source, actor=request.user)
    messages.success(request, "Campaign duplicated as a new draft.")
    return redirect(
        "communications:campaign_edit", site_id=site_id, campaign_id=campaign.id
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def unsubscribe_view(request, token):
    site = getattr(request, "site", None)
    if site is None:
        raise Http404("Unsubscribe link not found.")
    if request.method == "POST":
        capability = unsubscribe(site=site, token=token)
        if capability is None:
            raise Http404("Unsubscribe link not found or already used.")
        return render(
            request,
            "communications/unsubscribed.html",
            {"site": site, "channel": capability.channel, "completed": True},
        )
    return render(
        request,
        "communications/unsubscribed.html",
        {"site": site, "token": token, "completed": False},
    )


@csrf_exempt
@require_POST
def provider_callback(request, provider):
    if provider == "resend":
        if not settings.RESEND_WEBHOOK_SECRET:
            return HttpResponse("Resend callbacks are not configured.", status=503)
        try:
            process_resend_webhook(
                body=request.body,
                webhook_id=request.headers.get("Svix-Id", ""),
                timestamp=request.headers.get("Svix-Timestamp", ""),
                signature=request.headers.get("Svix-Signature", ""),
            )
        except (KeyError, TypeError, UnicodeDecodeError, ValueError):
            return HttpResponseBadRequest("Invalid Resend callback.")
        return HttpResponse(status=200)
    if not settings.COMMUNICATIONS_WEBHOOK_SECRET:
        return HttpResponse("Communication callbacks are not configured.", status=503)
    signature = request.headers.get("X-Communications-Signature", "")
    expected = hmac.new(
        settings.COMMUNICATIONS_WEBHOOK_SECRET.encode("utf-8"),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return HttpResponseBadRequest("Invalid callback signature.")
    try:
        payload = json.loads(request.body)
        required = ("event_id", "message_id", "event_type")
        if not all(payload.get(field) for field in required):
            raise ValueError
        process_provider_callback(
            provider=provider[:50],
            provider_event_id=str(payload["event_id"])[:255],
            provider_message_id=str(payload["message_id"])[:255],
            event_type=str(payload["event_type"])[:50],
            occurred_at=payload.get("occurred_at"),
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return HttpResponseBadRequest("Invalid callback payload.")
    return HttpResponse(status=200)
