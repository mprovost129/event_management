import math
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from events.models import EventOccurrence
from ops.services import record_audit_event
from subscriptions.gateway import billing_options

from .exports import site_export
from .forms import ExistingManagerForm, SiteOnboardingForm
from .models import SiteRole
from .permissions import (
    site_dashboard_required,
    site_staff_required,
    subscriber_admin_required,
    subscriber_recovery_required,
)
from .readiness import pilot_readiness
from .reporting import event_comparison, occurrence_comparison, site_summary
from .services import (
    SiteCreationNotAllowed,
    create_subscriber_site,
    site_setup_progress,
    subscriber_site_creation_decision,
    user_site_roles,
)

# How long after an event finishes the dashboard keeps offering to start a
# photo album. Long enough to cover a busy week, short enough that the
# dashboard is not nagging about something from last season.
ALBUM_PROMPT_DAYS = 30


@login_required
def account_dashboard(request):
    roles = user_site_roles(request.user)
    decision = subscriber_site_creation_decision(request.user)
    return render(
        request,
        "sites/account_dashboard.html",
        {
            "roles": roles,
            "can_create_site": decision.allowed,
            "site_creation_reason": decision.reason,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def onboarding(request):
    if not request.user.is_email_verified:
        raise PermissionDenied
    decision = subscriber_site_creation_decision(request.user)
    if not decision.allowed:
        return render(
            request,
            "sites/onboarding.html",
            {
                "form": None,
                "can_create_site": False,
                "site_creation_reason": decision.reason,
            },
            status=403 if request.method == "POST" else 200,
        )
    form = SiteOnboardingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            site = create_subscriber_site(
                owner=request.user,
                display_name=form.cleaned_data["display_name"],
                slug=form.cleaned_data["slug"],
                timezone_name=form.cleaned_data["timezone"],
                template_key=form.cleaned_data["template_key"],
                request=request,
            )
        except SiteCreationNotAllowed as exc:
            return render(
                request,
                "sites/onboarding.html",
                {
                    "form": None,
                    "can_create_site": False,
                    "site_creation_reason": str(exc),
                },
                status=403,
            )
        except IntegrityError:
            form.add_error("slug", "That site address was just claimed. Try another.")
        else:
            messages.success(request, "Your site and 14-day trial are ready.")
            return redirect("sites:dashboard", site_id=site.id)
    return render(
        request,
        "sites/onboarding.html",
        {"form": form, "can_create_site": True},
    )


@site_dashboard_required
def dashboard(request, site_id):
    site = request.authorized_site
    subscription = site.platform_subscription
    remaining_seconds = max(
        0, (subscription.trial_ends_at - timezone.now()).total_seconds()
    )
    setup = None
    if (
        request.site_role.role == SiteRole.Role.SUBSCRIBER_ADMIN
        and site.accepts_public_traffic
    ):
        setup = site_setup_progress(site)
        action_urls = {
            "website": reverse("content:presentation", kwargs={"site_id": site.id}),
            "event": reverse("events:create", kwargs={"site_id": site.id}),
            "contacts": reverse("contacts:create", kwargs={"site_id": site.id}),
            "stripe": reverse("payments:manage", kwargs={"site_id": site.id}),
            "subscription": f"{request.path}#subscription",
        }
        for check in setup["checks"]:
            check["action_url"] = action_urls[check["key"]]

    upcoming_occurrence = None
    if site.accepts_public_traffic:
        upcoming_occurrence = (
            EventOccurrence.objects.for_site(site)
            .filter(
                status=EventOccurrence.Status.SCHEDULED,
                ends_at__gte=timezone.now(),
            )
            .select_related("event")
            .first()
        )

    # After an event finishes, the most likely next thing a group wants to do
    # is post photos. Surface that instead of making them navigate to Events,
    # then Photo albums, then Create, then find the date in a dropdown.
    album_prompt = None
    if site.accepts_public_traffic:
        album_prompt = (
            EventOccurrence.objects.for_site(site)
            .filter(
                status=EventOccurrence.Status.SCHEDULED,
                ends_at__lte=timezone.now(),
                ends_at__gte=timezone.now() - timedelta(days=ALBUM_PROMPT_DAYS),
                albums__isnull=True,
            )
            .select_related("event")
            .order_by("-starts_at")
            .first()
        )

    from workspace.models import Activity, WorkTask

    context = {
        "site": site,
        "site_role": request.site_role,
        "subscription": subscription,
        "trial_days_remaining": math.ceil(remaining_seconds / 86400),
        "managers": site.roles.filter(
            role=SiteRole.Role.SITE_MANAGER, is_active=True
        ).select_related("user"),
        "manager_form": ExistingManagerForm(),
        "billing_options": billing_options(),
        "summary": site_summary(site),
        "canonical_domain": site.domains.filter(is_canonical=True).first(),
        "setup": setup,
        "upcoming_occurrence": upcoming_occurrence,
        "album_prompt": album_prompt,
        "workspace_activities": Activity.objects.for_site(site).select_related("actor")[
            :8
        ],
        "open_tasks": WorkTask.objects.for_site(site)
        .exclude(status=WorkTask.Status.DONE)
        .select_related("assignee", "event")[:6],
    }
    return render(request, "sites/dashboard.html", context)


@site_staff_required
def quick_start(request, site_id):
    """Guided first-run workspace for administrators and site managers."""
    site = request.authorized_site
    setup = site_setup_progress(site)
    action_urls = {
        "website": reverse("content:presentation", kwargs={"site_id": site.id}),
        "event": reverse("events:create", kwargs={"site_id": site.id}),
        "contacts": reverse("contacts:create", kwargs={"site_id": site.id}),
        "stripe": reverse("payments:manage", kwargs={"site_id": site.id}),
        "subscription": f"{reverse('sites:dashboard', kwargs={'site_id': site.id})}#subscription",
    }
    for check in setup["checks"]:
        check["action_url"] = action_urls[check["key"]]

    from content.models import BlogPost, PublishingStatus, SitePage
    from workspace.models import AutomationRule, Document, IntakeForm, WorkTask

    growth_steps = [
        {
            "label": "Complete your public pages",
            "description": "Publish the About and Contact pages so visitors know who you are and how to reach you.",
            "complete": SitePage.objects.for_site(site)
            .filter(
                page_type__in=(SitePage.PageType.ABOUT, SitePage.PageType.CONTACT),
                status=PublishingStatus.PUBLISHED,
            )
            .count()
            >= 2,
            "action_url": reverse("content:manage", kwargs={"site_id": site.id}),
        },
        {
            "label": "Share your first update",
            "description": "Publish a blog post or announcement to make the site feel active.",
            "complete": BlogPost.objects.for_site(site)
            .filter(status=PublishingStatus.PUBLISHED)
            .exists(),
            "action_url": reverse("content:blog_create", kwargs={"site_id": site.id}),
        },
        {
            "label": "Create an operating task",
            "description": "Assign a follow-up, deadline, or event preparation item to your team.",
            "complete": WorkTask.objects.for_site(site).exists(),
            "action_url": reverse("workspace:task_create", kwargs={"site_id": site.id}),
        },
        {
            "label": "Create a form or waiver",
            "description": "Collect information, applications, volunteer interest, or signed waivers.",
            "complete": IntakeForm.objects.for_site(site).exists(),
            "action_url": reverse(
                "workspace:intake_form_create", kwargs={"site_id": site.id}
            ),
        },
        {
            "label": "Upload an organization document",
            "description": "Store a contract, policy, flyer, insurance certificate, or waiver.",
            "complete": Document.objects.for_site(site).exists(),
            "action_url": reverse(
                "workspace:document_upload", kwargs={"site_id": site.id}
            ),
        },
        {
            "label": "Create your first automation",
            "description": "Automatically create a task, tag a contact, or record activity after a form response.",
            "complete": AutomationRule.objects.for_site(site).exists(),
            "action_url": reverse(
                "workspace:automation_create", kwargs={"site_id": site.id}
            ),
        },
    ]
    growth_completed = sum(step["complete"] for step in growth_steps)
    return render(
        request,
        "sites/quick_start.html",
        {
            "site": site,
            "site_role": request.site_role,
            "setup": setup,
            "growth_steps": growth_steps,
            "growth_completed": growth_completed,
            "growth_total": len(growth_steps),
            "growth_percent": round(growth_completed * 100 / len(growth_steps)),
            "canonical_domain": site.domains.filter(is_canonical=True).first(),
        },
    )


@site_staff_required
def reports(request, site_id):
    site = request.authorized_site
    view_filter = request.GET.get("view", "all")
    if view_filter not in {"all", "upcoming", "completed"}:
        view_filter = "all"
    all_occurrences = occurrence_comparison(site)
    occurrences = all_occurrences
    if view_filter == "upcoming":
        occurrences = [
            row
            for row in occurrences
            if not row["is_complete"] and not row["is_canceled"]
        ]
    elif view_filter == "completed":
        occurrences = [
            row for row in occurrences if row["is_complete"] and not row["is_canceled"]
        ]
    return render(
        request,
        "sites/reports.html",
        {
            "site": site,
            "summary": site_summary(site),
            "occurrences": occurrences,
            "events": event_comparison(site, occurrence_rows=all_occurrences),
            "view_filter": view_filter,
        },
    )


@subscriber_recovery_required
def launch_center(request, site_id):
    site = request.authorized_site
    readiness = pilot_readiness(site)
    occurrence = readiness["occurrence"]
    dashboard_url = reverse("sites:dashboard", kwargs={"site_id": site.id})
    action_urls = {
        "subscriber_admin": dashboard_url,
        "site_published": reverse("content:presentation", kwargs={"site_id": site.id}),
        "active_access": f"{dashboard_url}#subscription",
        "contacts_entered": reverse("contacts:create", kwargs={"site_id": site.id}),
        "upcoming_event": reverse("events:create", kwargs={"site_id": site.id}),
        "commerce_ready": reverse("payments:manage", kwargs={"site_id": site.id}),
        # Both live on the website settings screen under "A couple of legal details".
        "refund_policy": reverse("content:presentation", kwargs={"site_id": site.id}),
        "mailing_address": reverse("content:presentation", kwargs={"site_id": site.id}),
        "billing_selected": f"{dashboard_url}#subscription",
        "backup_manager": f"{dashboard_url}#managers",
        "data_exported": reverse("sites:export_data", kwargs={"site_id": site.id}),
    }
    if occurrence:
        action_urls.update(
            {
                "invitation_path": reverse(
                    "events:invite",
                    kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
                ),
                "venue_complete": reverse(
                    "events:occurrence_edit",
                    kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
                ),
                "response_recorded": reverse(
                    "attendance:roster",
                    kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
                ),
                "delivery_tested": reverse(
                    "events:invite",
                    kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
                ),
            }
        )
    else:
        event_url = reverse("events:create", kwargs={"site_id": site.id})
        action_urls.update(
            {
                "invitation_path": event_url,
                "venue_complete": event_url,
                "response_recorded": event_url,
                "delivery_tested": event_url,
            }
        )
    action_labels = {
        "subscriber_admin": "Review access",
        "site_published": "Website settings",
        "active_access": "Review billing",
        "contacts_entered": "Add a contact",
        "upcoming_event": "Create an event",
        "commerce_ready": "Open payments",
        "refund_policy": "Set refund policy",
        "mailing_address": "Add mailing address",
        "invitation_path": "Open invitations",
        "billing_selected": "Choose billing",
        "venue_complete": "Edit occurrence",
        "response_recorded": "Open roster",
        "delivery_tested": "Send a test invitation",
        "backup_manager": "Manage team",
        "data_exported": "Download export",
    }
    for check in readiness["required"] + readiness["recommended"]:
        check["action_url"] = action_urls[check["key"]]
        check["action_label"] = action_labels[check["key"]]
        if check["key"] == "commerce_ready" and occurrence is None:
            check["status_label"] = "After event"
        elif (
            check["key"] == "commerce_ready"
            and check["complete"]
            and not readiness["ticketed"]
        ):
            check["status_label"] = "Not needed"
        else:
            check["status_label"] = "Complete" if check["complete"] else "To do"
    return render(
        request,
        "sites/launch_center.html",
        {"site": site, "readiness": readiness},
    )


@subscriber_recovery_required
def export_data(request, site_id):
    site = request.authorized_site
    record_audit_event(
        action="site.data_exported",
        actor=request.user,
        site_id=site.id,
        target=site,
        summary={"format": "gather-hqs-site-export-v1"},
        request=request,
    )
    response = JsonResponse(site_export(site), encoder=DjangoJSONEncoder)
    response["Content-Disposition"] = f'attachment; filename="{site.slug}-export.json"'
    return response


@require_POST
@subscriber_admin_required
def add_manager(request, site_id):
    form = ExistingManagerForm(request.POST)
    if form.is_valid():
        manager = form.user
        if manager == request.user:
            messages.error(request, "The subscriber admin already has full access.")
        else:
            role, created = SiteRole.objects.update_or_create(
                site=request.authorized_site,
                user=manager,
                defaults={
                    "role": SiteRole.Role.SITE_MANAGER,
                    "is_active": True,
                    "invited_by": request.user,
                },
            )
            if created:
                record_audit_event(
                    action="site.manager.added",
                    actor=request.user,
                    site_id=request.authorized_site.id,
                    target=role,
                    summary={"manager_user_id": str(manager.id)},
                    request=request,
                )
            messages.success(request, f"{manager.email} is now a site manager.")
    else:
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
    return redirect("sites:dashboard", site_id=site_id)


@require_POST
@subscriber_admin_required
@transaction.atomic
def remove_manager(request, site_id, role_id):
    role = request.authorized_site.roles.filter(
        pk=role_id, role=SiteRole.Role.SITE_MANAGER, is_active=True
    ).first()
    if role is None:
        messages.error(request, "That manager assignment was not found.")
    else:
        role.is_active = False
        role.save(update_fields=("is_active", "updated_at"))
        record_audit_event(
            action="site.manager.removed",
            actor=request.user,
            site_id=request.authorized_site.id,
            target=role,
            summary={"manager_user_id": str(role.user_id)},
            request=request,
        )
        messages.success(request, "Site manager access was removed.")
    return redirect("sites:dashboard", site_id=site_id)
