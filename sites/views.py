import math

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from ops.services import record_audit_event
from subscriptions.gateway import billing_options

from .exports import site_export
from .forms import ExistingManagerForm, SiteOnboardingForm
from .models import SiteRole
from .permissions import site_staff_required, subscriber_admin_required
from .reporting import event_comparison, site_summary
from .services import create_subscriber_site, user_site_roles


@login_required
def account_dashboard(request):
    roles = user_site_roles(request.user)
    return render(request, "sites/account_dashboard.html", {"roles": roles})


@login_required
@require_http_methods(["GET", "POST"])
def onboarding(request):
    if not request.user.is_email_verified:
        raise PermissionDenied
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
        except IntegrityError:
            form.add_error("slug", "That site address was just claimed. Try another.")
        else:
            messages.success(request, "Your site and 14-day trial are ready.")
            return redirect("sites:dashboard", site_id=site.id)
    return render(request, "sites/onboarding.html", {"form": form})


@site_staff_required
def dashboard(request, site_id):
    site = request.authorized_site
    subscription = site.platform_subscription
    remaining_seconds = max(
        0, (subscription.trial_ends_at - timezone.now()).total_seconds()
    )
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
    }
    return render(request, "sites/dashboard.html", context)


@site_staff_required
def reports(request, site_id):
    site = request.authorized_site
    return render(
        request,
        "sites/reports.html",
        {"site": site, "summary": site_summary(site), "events": event_comparison(site)},
    )


@subscriber_admin_required
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
