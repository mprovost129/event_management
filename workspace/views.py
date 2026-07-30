import csv
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from contacts.models import Contact
from core.exports import spreadsheet_safe_cell
from core.pagination import paginate
from sites.models import SiteRole
from sites.permissions import site_staff_required

from .ai_services import generate_content
from .forms import (
    AIContentDraftForm,
    AutomationRuleForm,
    ChecklistItemForm,
    CommentForm,
    DocumentForm,
    IntakeFormBuilderForm,
    SponsorForm,
    SponsorshipForm,
    TaskForm,
    VolunteerAssignmentForm,
    VolunteerHourForm,
    VolunteerProfileForm,
    VolunteerShiftForm,
    build_public_intake_form,
)
from .models import (
    Activity,
    AIContentDraft,
    AutomationRule,
    AutomationRun,
    Document,
    IntakeForm,
    IntakeSubmission,
    Sponsor,
    VolunteerProfile,
    VolunteerShift,
    WorkTask,
)
from .reporting import organization_insights
from .services import (
    dispatch_automation_trigger,
    record_activity,
    run_automation_rule,
)


@site_staff_required
def task_list(request, site_id):
    site = request.authorized_site
    status = request.GET.get("status", "open")
    tasks = WorkTask.objects.for_site(site).select_related("event", "assignee")
    if status == "done":
        tasks = tasks.filter(status=WorkTask.Status.DONE)
    elif status == "all":
        pass
    else:
        status = "open"
        tasks = tasks.exclude(status=WorkTask.Status.DONE)
    tasks = paginate(request, tasks)
    return render(
        request,
        "workspace/task_list.html",
        {
            "site": site,
            "tasks": tasks,
            "selected_status": status,
            "page_obj": tasks,
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def task_create(request, site_id):
    site = request.authorized_site
    form = TaskForm(
        request.POST or None, site=site, initial={"event": request.GET.get("event")}
    )
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.site = site
        task.created_by = request.user
        task.full_clean()
        task.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Created task: {task.title}",
            kind="task",
            target_url=reverse(
                "workspace:task_detail", kwargs={"site_id": site.id, "task_id": task.id}
            ),
        )
        messages.success(request, "Task created.")
        return redirect("workspace:task_detail", site_id=site.id, task_id=task.id)
    return render(
        request,
        "workspace/task_form.html",
        {"site": site, "form": form, "heading": "Create task"},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def task_detail(request, site_id, task_id):
    site = request.authorized_site
    task = get_object_or_404(
        WorkTask.objects.for_site(site).select_related("event", "assignee"), pk=task_id
    )
    form = TaskForm(request.POST or None, instance=task, site=site)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.full_clean()
        task.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Updated task: {task.title}",
            kind="task",
            target_url=request.path,
        )
        messages.success(request, "Task updated.")
        return redirect(request.path)
    return render(
        request,
        "workspace/task_detail.html",
        {
            "site": site,
            "task": task,
            "form": form,
            "checklist_form": ChecklistItemForm(),
            "comment_form": CommentForm(),
        },
    )


@site_staff_required
@require_POST
def checklist_add(request, site_id, task_id):
    site = request.authorized_site
    task = get_object_or_404(WorkTask.objects.for_site(site), pk=task_id)
    form = ChecklistItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.task = task
        item.save()
    return redirect("workspace:task_detail", site_id=site.id, task_id=task.id)


@site_staff_required
@require_POST
def checklist_toggle(request, site_id, task_id, item_id):
    site = request.authorized_site
    task = get_object_or_404(WorkTask.objects.for_site(site), pk=task_id)
    item = get_object_or_404(task.checklist_items, pk=item_id)
    item.is_complete = not item.is_complete
    item.save(update_fields=("is_complete",))
    return redirect("workspace:task_detail", site_id=site.id, task_id=task.id)


@site_staff_required
@require_POST
def comment_add(request, site_id, task_id):
    site = request.authorized_site
    task = get_object_or_404(WorkTask.objects.for_site(site), pk=task_id)
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
    return redirect("workspace:task_detail", site_id=site.id, task_id=task.id)


@site_staff_required
def document_list(request, site_id):
    site = request.authorized_site
    documents = Document.objects.for_site(site).select_related(
        "event", "contact", "task", "uploaded_by"
    )
    if request.site_role.role != SiteRole.Role.SUBSCRIBER_ADMIN:
        documents = documents.exclude(visibility=Document.Visibility.ADMIN)
    query = request.GET.get("q", "").strip()
    if query:
        documents = documents.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(category__icontains=query)
        )
    documents = paginate(request, documents)
    return render(
        request,
        "workspace/document_list.html",
        {
            "site": site,
            "documents": documents,
            "query": query,
            "page_obj": documents,
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def document_upload(request, site_id):
    site = request.authorized_site
    initial = {
        "event": request.GET.get("event"),
        "contact": request.GET.get("contact"),
        "task": request.GET.get("task"),
    }
    form = DocumentForm(
        request.POST or None,
        request.FILES or None,
        site=site,
        initial=initial,
        can_manage_admin_documents=(
            request.site_role.role == SiteRole.Role.SUBSCRIBER_ADMIN
        ),
    )
    if request.method == "POST" and form.is_valid():
        document = form.save(commit=False)
        document.site = site
        document.uploaded_by = request.user
        document.full_clean()
        document.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Uploaded document: {document.title}",
            kind="document",
            target_url=reverse("workspace:document_list", kwargs={"site_id": site.id}),
        )
        messages.success(request, "Document uploaded.")
        return redirect("workspace:document_list", site_id=site.id)
    return render(request, "workspace/document_form.html", {"site": site, "form": form})


@site_staff_required
def document_download(request, site_id, document_id):
    site = request.authorized_site
    document = get_object_or_404(Document.objects.for_site(site), pk=document_id)
    if (
        document.visibility == Document.Visibility.ADMIN
        and request.site_role.role != SiteRole.Role.SUBSCRIBER_ADMIN
    ):
        raise PermissionDenied
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=Path(document.file.name).name,
    )


@site_staff_required
@require_POST
def document_delete(request, site_id, document_id):
    site = request.authorized_site
    document = get_object_or_404(Document.objects.for_site(site), pk=document_id)
    if (
        document.visibility == Document.Visibility.ADMIN
        and request.site_role.role != SiteRole.Role.SUBSCRIBER_ADMIN
    ):
        raise PermissionDenied
    title = document.title
    document.file.delete(save=False)
    document.delete()
    record_activity(
        site=site,
        actor=request.user,
        verb=f"Deleted document: {title}",
        kind="document",
    )
    messages.success(request, "Document deleted.")
    return redirect("workspace:document_list", site_id=site.id)


@site_staff_required
def activity_list(request, site_id):
    site = request.authorized_site
    activities = paginate(
        request,
        Activity.objects.for_site(site).select_related("actor"),
        per_page=50,
    )
    return render(
        request,
        "workspace/activity_list.html",
        {
            "site": site,
            "activities": activities,
            "page_obj": activities,
        },
    )


@site_staff_required
def volunteer_list(request, site_id):
    site = request.authorized_site
    volunteers = (
        VolunteerProfile.objects.for_site(site)
        .select_related("contact")
        .prefetch_related("hour_entries")
    )
    volunteers = paginate(request, volunteers)
    shifts = (
        VolunteerShift.objects.for_site(site)
        .select_related("event")
        .prefetch_related("assignments")[:20]
    )
    return render(
        request,
        "workspace/volunteer_list.html",
        {
            "site": site,
            "volunteers": volunteers,
            "shifts": shifts,
            "page_obj": volunteers,
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def volunteer_create(request, site_id):
    site = request.authorized_site
    form = VolunteerProfileForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.site = site
        obj.full_clean()
        obj.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Added volunteer: {obj.contact.display_name}",
            kind="volunteer",
        )
        messages.success(request, "Volunteer added.")
        return redirect(
            "workspace:volunteer_detail", site_id=site.id, volunteer_id=obj.id
        )
    return render(
        request,
        "workspace/generic_form.html",
        {"site": site, "form": form, "heading": "Add volunteer"},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def volunteer_detail(request, site_id, volunteer_id):
    site = request.authorized_site
    obj = get_object_or_404(
        VolunteerProfile.objects.for_site(site).select_related("contact"),
        pk=volunteer_id,
    )
    form = VolunteerProfileForm(request.POST or None, instance=obj, site=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Volunteer updated.")
        return redirect(request.path)
    return render(
        request,
        "workspace/volunteer_detail.html",
        {
            "site": site,
            "volunteer": obj,
            "form": form,
            "hour_form": VolunteerHourForm(site=site, volunteer=obj),
        },
    )


@site_staff_required
@require_POST
def volunteer_hour_add(request, site_id, volunteer_id):
    site = request.authorized_site
    volunteer = get_object_or_404(
        VolunteerProfile.objects.for_site(site), pk=volunteer_id
    )
    form = VolunteerHourForm(request.POST, site=site, volunteer=volunteer)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.site = site
        obj.volunteer = volunteer
        obj.approved_by = request.user
        obj.full_clean()
        obj.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Logged {obj.hours} volunteer hours for {volunteer.contact.display_name}",
            kind="volunteer",
        )
    else:
        messages.error(request, "Please correct the volunteer hours entry.")
    return redirect(
        "workspace:volunteer_detail", site_id=site.id, volunteer_id=volunteer.id
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def shift_create(request, site_id):
    site = request.authorized_site
    form = VolunteerShiftForm(
        request.POST or None, site=site, initial={"event": request.GET.get("event")}
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.site = site
        obj.full_clean()
        obj.save()
        messages.success(request, "Volunteer shift created.")
        return redirect("workspace:shift_detail", site_id=site.id, shift_id=obj.id)
    return render(
        request,
        "workspace/generic_form.html",
        {"site": site, "form": form, "heading": "Create volunteer shift"},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def shift_detail(request, site_id, shift_id):
    site = request.authorized_site
    shift = get_object_or_404(
        VolunteerShift.objects.for_site(site).select_related("event"), pk=shift_id
    )
    form = VolunteerShiftForm(request.POST or None, instance=shift, site=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Shift updated.")
        return redirect(request.path)
    return render(
        request,
        "workspace/shift_detail.html",
        {
            "site": site,
            "shift": shift,
            "form": form,
            "assignment_form": VolunteerAssignmentForm(site=site),
        },
    )


@site_staff_required
@require_POST
def shift_assign(request, site_id, shift_id):
    site = request.authorized_site
    shift = get_object_or_404(VolunteerShift.objects.for_site(site), pk=shift_id)
    form = VolunteerAssignmentForm(request.POST, site=site)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.shift = shift
        obj.full_clean()
        obj.save()
        messages.success(request, "Volunteer assigned.")
    else:
        messages.error(request, "That volunteer could not be assigned.")
    return redirect("workspace:shift_detail", site_id=site.id, shift_id=shift.id)


@site_staff_required
def sponsor_list(request, site_id):
    site = request.authorized_site
    sponsors = paginate(
        request, Sponsor.objects.for_site(site).prefetch_related("sponsorships")
    )
    return render(
        request,
        "workspace/sponsor_list.html",
        {"site": site, "sponsors": sponsors, "page_obj": sponsors},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def sponsor_create(request, site_id):
    site = request.authorized_site
    form = SponsorForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.site = site
        obj.save()
        messages.success(request, "Sponsor added.")
        return redirect("workspace:sponsor_detail", site_id=site.id, sponsor_id=obj.id)
    return render(
        request,
        "workspace/generic_form.html",
        {"site": site, "form": form, "heading": "Add sponsor", "multipart": True},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def sponsor_detail(request, site_id, sponsor_id):
    site = request.authorized_site
    sponsor = get_object_or_404(Sponsor.objects.for_site(site), pk=sponsor_id)
    form = SponsorForm(request.POST or None, request.FILES or None, instance=sponsor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Sponsor updated.")
        return redirect(request.path)
    return render(
        request,
        "workspace/sponsor_detail.html",
        {
            "site": site,
            "sponsor": sponsor,
            "form": form,
            "sponsorship_form": SponsorshipForm(site=site),
        },
    )


@site_staff_required
@require_POST
def sponsorship_add(request, site_id, sponsor_id):
    site = request.authorized_site
    sponsor = get_object_or_404(Sponsor.objects.for_site(site), pk=sponsor_id)
    form = SponsorshipForm(request.POST, site=site)
    if form.is_valid():
        obj = form.save(commit=False)
        obj.site = site
        obj.sponsor = sponsor
        obj.full_clean()
        obj.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Added sponsorship: {sponsor.name} — {obj.level or obj.get_status_display()}",
            kind="sponsor",
        )
        messages.success(request, "Sponsorship added.")
    else:
        messages.error(request, "Please correct the sponsorship details.")
    return redirect("workspace:sponsor_detail", site_id=site.id, sponsor_id=sponsor.id)


@site_staff_required
def intake_form_list(request, site_id):
    site = request.authorized_site
    forms_qs = (
        IntakeForm.objects.for_site(site)
        .select_related("event")
        .annotate(response_count=models.Count("submissions"))
    )
    forms_qs = paginate(request, forms_qs, per_page=24)
    return render(
        request,
        "workspace/intake_form_list.html",
        {"site": site, "intake_forms": forms_qs, "page_obj": forms_qs},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def intake_form_create(request, site_id):
    site = request.authorized_site
    form = IntakeFormBuilderForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        record_activity(
            site=site,
            actor=request.user,
            verb=f"Created form: {obj.title}",
            kind="form",
            target_url=reverse(
                "workspace:intake_form_detail",
                kwargs={"site_id": site.id, "form_id": obj.id},
            ),
        )
        messages.success(request, "Form created.")
        return redirect("workspace:intake_form_detail", site_id=site.id, form_id=obj.id)
    return render(
        request,
        "workspace/intake_form_builder.html",
        {"site": site, "form": form, "heading": "Create form"},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def intake_form_detail(request, site_id, form_id):
    site = request.authorized_site
    obj = get_object_or_404(
        IntakeForm.objects.for_site(site).select_related("event"), pk=form_id
    )
    form = IntakeFormBuilderForm(request.POST or None, instance=obj, site=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Form updated.")
        return redirect(request.path)
    submissions = obj.submissions.select_related("contact")[:100]
    public_url = request.build_absolute_uri(
        reverse("workspace:intake_public", kwargs={"form_id": obj.id, "slug": obj.slug})
    )
    return render(
        request,
        "workspace/intake_form_detail.html",
        {
            "site": site,
            "intake_form": obj,
            "form": form,
            "submissions": submissions,
            "public_url": public_url,
        },
    )


@site_staff_required
def intake_submission_detail(request, site_id, form_id, submission_id):
    site = request.authorized_site
    intake_form = get_object_or_404(IntakeForm.objects.for_site(site), pk=form_id)
    submission = get_object_or_404(
        IntakeSubmission.objects.for_site(site).select_related("contact"),
        pk=submission_id,
        intake_form=intake_form,
    )
    return render(
        request,
        "workspace/intake_submission_detail.html",
        {"site": site, "intake_form": intake_form, "submission": submission},
    )


def intake_public(request, form_id, slug):
    intake_form = get_object_or_404(
        IntakeForm.objects.select_related("site", "event"), pk=form_id, slug=slug
    )
    if not intake_form.site.accepts_public_traffic or not intake_form.site.is_published:
        raise Http404
    if not intake_form.accepts_responses:
        return render(
            request,
            "workspace/intake_closed.html",
            {"intake_form": intake_form},
            status=410,
        )
    form = build_public_intake_form(intake_form, request.POST or None)
    if request.method == "POST" and form.is_valid():
        response_data = {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in form.cleaned_data.items()
            if key not in {"signature_name", "agreement_accepted"}
        }
        email = str(response_data.get("email", "")).strip()
        first_name = str(response_data.get("first_name", "")).strip()
        last_name = str(response_data.get("last_name", "")).strip()
        contact = None
        if intake_form.create_or_update_contact and email:
            contact = (
                Contact.objects.for_site(intake_form.site)
                .filter(normalized_email=email.casefold())
                .first()
            )
            if contact:
                changed = False
                if first_name and not contact.first_name:
                    contact.first_name = first_name
                    changed = True
                if last_name and not contact.last_name:
                    contact.last_name = last_name
                    changed = True
                if changed:
                    contact.save()
            else:
                contact = Contact.objects.create(
                    site=intake_form.site,
                    first_name=first_name or "Form",
                    last_name=last_name or "Response",
                    email=email,
                )
        submission = IntakeSubmission(
            site=intake_form.site,
            intake_form=intake_form,
            contact=contact,
            response_data=response_data,
            submitter_name=f"{first_name} {last_name}".strip(),
            submitter_email=email,
            signature_name=form.cleaned_data.get("signature_name", ""),
            agreed_at=timezone.now() if intake_form.require_signature else None,
            source_ip=request.META.get("REMOTE_ADDR") or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )
        submission.full_clean()
        submission.save()
        dispatch_automation_trigger(
            site=intake_form.site,
            trigger=AutomationRule.Trigger.FORM_SUBMITTED,
            trigger_data={
                "form_id": str(intake_form.id),
                "form_title": intake_form.title,
                "submitter_name": submission.submitter_name,
                "submitter_email": submission.submitter_email,
            },
            contact=contact,
        )
        record_activity(
            site=intake_form.site,
            actor=None,
            verb=f"Received form response: {intake_form.title}",
            detail=submission.submitter_name or submission.submitter_email,
            kind="form",
            target_url=reverse(
                "workspace:intake_submission_detail",
                kwargs={
                    "site_id": intake_form.site_id,
                    "form_id": intake_form.id,
                    "submission_id": submission.id,
                },
            ),
        )
        return render(
            request, "workspace/intake_thanks.html", {"intake_form": intake_form}
        )
    return render(
        request,
        "workspace/intake_public.html",
        {"intake_form": intake_form, "form": form},
    )


@site_staff_required
def automation_list(request, site_id):
    site = request.authorized_site
    rules = paginate(
        request, AutomationRule.objects.for_site(site).prefetch_related("runs")
    )
    recent_runs = AutomationRun.objects.for_site(site).select_related("rule")[:25]
    return render(
        request,
        "workspace/automation_list.html",
        {
            "site": site,
            "rules": rules,
            "recent_runs": recent_runs,
            "page_obj": rules,
        },
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def automation_create(request, site_id):
    site = request.authorized_site
    form = AutomationRuleForm(request.POST or None, site=site)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.created_by = request.user
        obj.save()
        messages.success(request, "Automation created.")
        return redirect("workspace:automation_detail", site_id=site.id, rule_id=obj.id)
    return render(
        request,
        "workspace/automation_form.html",
        {"site": site, "form": form, "heading": "Create automation"},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def automation_detail(request, site_id, rule_id):
    site = request.authorized_site
    rule = get_object_or_404(AutomationRule.objects.for_site(site), pk=rule_id)
    form = AutomationRuleForm(request.POST or None, instance=rule, site=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Automation updated.")
        return redirect(request.path)
    return render(
        request,
        "workspace/automation_detail.html",
        {"site": site, "rule": rule, "form": form, "runs": rule.runs.all()[:50]},
    )


@site_staff_required
@require_POST
def automation_run(request, site_id, rule_id):
    site = request.authorized_site
    rule = get_object_or_404(AutomationRule.objects.for_site(site), pk=rule_id)
    run = run_automation_rule(rule, trigger_data={"manual": True}, actor=request.user)
    if run.status == AutomationRun.Status.SUCCEEDED:
        messages.success(request, "Automation completed successfully.")
    elif run.status == AutomationRun.Status.SKIPPED:
        messages.warning(request, run.result_detail or "Automation was skipped.")
    else:
        messages.error(
            request, "Automation failed. Review the run history for details."
        )
    return redirect("workspace:automation_detail", site_id=site.id, rule_id=rule.id)


@site_staff_required
def insights(request, site_id):
    site = request.authorized_site
    return render(
        request,
        "workspace/insights.html",
        {"site": site, "insights": organization_insights(site)},
    )


@site_staff_required
def insights_export(request, site_id):
    site = request.authorized_site
    data = organization_insights(site)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{site.slug}-organization-report.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(
        ["Gather HQs organization report", spreadsheet_safe_cell(site.display_name)]
    )
    writer.writerow(["Generated", data["generated_at"].isoformat()])
    writer.writerow([])
    writer.writerow(["Section", "Metric", "Value"])
    rows = [
        ("People", "Active contacts", data["contacts"]["total"]),
        ("People", "New contacts, last 30 days", data["contacts"]["new_30_days"]),
        ("People", "Active members", data["contacts"]["members"]),
        ("People", "Email consent granted", data["contacts"]["email_opted_in"]),
        ("Tasks", "Open", data["tasks"]["open"]),
        ("Tasks", "Overdue", data["tasks"]["overdue"]),
        ("Tasks", "Due in next 7 days", data["tasks"]["due_soon"]),
        ("Tasks", "Completion rate", f"{data['tasks']['completion_rate']}%"),
        ("Documents", "Total", data["documents"]["total"]),
        ("Forms", "Total submissions", data["forms"]["submissions"]),
        ("Forms", "Submissions, last 30 days", data["forms"]["submissions_30_days"]),
        ("Forms", "Signed waivers", data["forms"]["signed_waivers"]),
        ("Volunteers", "Active volunteers", data["volunteers"]["active"]),
        ("Volunteers", "Total service hours", data["volunteers"]["total_hours"]),
        ("Sponsors", "Committed sponsorships", data["sponsors"]["committed_display"]),
        ("Sponsors", "Paid sponsorships", data["sponsors"]["paid_display"]),
        ("Automations", "Active rules", data["automations"]["active_rules"]),
        (
            "Automations",
            "Success rate, last 30 days",
            f"{data['automations']['success_rate']}%",
        ),
    ]
    writer.writerows([spreadsheet_safe_cell(value) for value in row] for row in rows)
    return response


@site_staff_required
def ai_draft_list(request, site_id):
    site = request.authorized_site
    drafts = paginate(
        request, AIContentDraft.objects.for_site(site).select_related("created_by")
    )
    return render(
        request,
        "workspace/ai_draft_list.html",
        {"site": site, "drafts": drafts, "page_obj": drafts},
    )


@site_staff_required
@require_http_methods(["GET", "POST"])
def ai_draft_create(request, site_id):
    site = request.authorized_site
    form = AIContentDraftForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        draft = form.save(commit=False)
        draft.site = site
        draft.created_by = request.user
        draft.save()
        try:
            output, provider, model_name = generate_content(draft)
            draft.output = output
            draft.provider = provider
            draft.model_name = model_name
            draft.status = AIContentDraft.Status.GENERATED
            draft.error_message = ""
            draft.save(
                update_fields=(
                    "output",
                    "provider",
                    "model_name",
                    "status",
                    "error_message",
                    "updated_at",
                )
            )
            record_activity(
                site=site,
                actor=request.user,
                verb=f"Generated AI content: {draft.title}",
                kind="ai",
                target_url=reverse(
                    "workspace:ai_draft_detail",
                    kwargs={"site_id": site.id, "draft_id": draft.id},
                ),
            )
            messages.success(request, "Content draft generated.")
        except RuntimeError as exc:
            draft.status = AIContentDraft.Status.FAILED
            draft.error_message = str(exc)
            draft.save(update_fields=("status", "error_message", "updated_at"))
            messages.error(
                request,
                "The content provider could not generate this draft. The request was saved for review.",
            )
        return redirect("workspace:ai_draft_detail", site_id=site.id, draft_id=draft.id)
    return render(request, "workspace/ai_draft_form.html", {"site": site, "form": form})


@site_staff_required
@require_http_methods(["GET", "POST"])
def ai_draft_detail(request, site_id, draft_id):
    site = request.authorized_site
    draft = get_object_or_404(
        AIContentDraft.objects.for_site(site).select_related("created_by"), pk=draft_id
    )
    form = AIContentDraftForm(request.POST or None, instance=draft)
    if request.method == "POST" and form.is_valid():
        draft = form.save()
        try:
            output, provider, model_name = generate_content(draft)
            draft.output = output
            draft.provider = provider
            draft.model_name = model_name
            draft.status = AIContentDraft.Status.GENERATED
            draft.error_message = ""
            draft.save(
                update_fields=(
                    "output",
                    "provider",
                    "model_name",
                    "status",
                    "error_message",
                    "updated_at",
                )
            )
            messages.success(request, "Content regenerated.")
        except RuntimeError as exc:
            draft.status = AIContentDraft.Status.FAILED
            draft.error_message = str(exc)
            draft.save(update_fields=("status", "error_message", "updated_at"))
            messages.error(
                request, "The content provider could not regenerate this draft."
            )
        return redirect(request.path)
    return render(
        request,
        "workspace/ai_draft_detail.html",
        {"site": site, "draft": draft, "form": form},
    )
