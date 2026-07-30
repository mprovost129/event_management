from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from contacts.models import Contact, Member

from .models import (
    Activity,
    AutomationRule,
    AutomationRun,
    Document,
    IntakeForm,
    IntakeSubmission,
    Sponsor,
    Sponsorship,
    VolunteerAssignment,
    VolunteerHourEntry,
    VolunteerProfile,
    WorkTask,
)


def _percent(numerator, denominator):
    return round((numerator * 100 / denominator), 1) if denominator else 0


def organization_insights(site, *, now=None):
    now = now or timezone.now()
    thirty_days_ago = now - timedelta(days=30)
    today = timezone.localdate()

    contacts = Contact.objects.for_site(site).filter(archived_at__isnull=True)
    members = Member.objects.for_site(site)
    tasks = WorkTask.objects.for_site(site)
    submissions = IntakeSubmission.objects.for_site(site)
    volunteers = VolunteerProfile.objects.for_site(site)
    sponsorships = Sponsorship.objects.for_site(site)
    automation_runs = AutomationRun.objects.for_site(site)

    open_tasks = tasks.exclude(status=WorkTask.Status.DONE)
    completed_tasks = tasks.filter(status=WorkTask.Status.DONE)
    overdue_tasks = open_tasks.filter(due_at__lt=now)
    due_soon_tasks = open_tasks.filter(
        due_at__gte=now, due_at__lt=now + timedelta(days=7)
    )

    volunteer_hours = VolunteerHourEntry.objects.for_site(site).aggregate(
        total=Sum("hours")
    )["total"] or Decimal("0")
    recent_volunteer_hours = VolunteerHourEntry.objects.for_site(site).filter(
        service_date__gte=thirty_days_ago.date()
    ).aggregate(total=Sum("hours"))["total"] or Decimal("0")

    committed_statuses = (
        Sponsorship.Status.COMMITTED,
        Sponsorship.Status.INVOICED,
        Sponsorship.Status.PAID,
    )
    committed_sponsorship_cents = (
        sponsorships.filter(status__in=committed_statuses).aggregate(
            total=Sum("amount_cents")
        )["total"]
        or 0
    )
    paid_sponsorship_cents = (
        sponsorships.filter(status=Sponsorship.Status.PAID).aggregate(
            total=Sum("amount_cents")
        )["total"]
        or 0
    )

    recent_runs = automation_runs.filter(created_at__gte=thirty_days_ago)
    successful_runs = recent_runs.filter(status=AutomationRun.Status.SUCCEEDED).count()

    monthly_contacts = list(
        contacts.filter(created_at__gte=now - timedelta(days=365))
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    monthly_submissions = list(
        submissions.filter(created_at__gte=now - timedelta(days=365))
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )

    form_performance = list(
        IntakeForm.objects.for_site(site)
        .annotate(
            response_count=Count("submissions"),
            recent_response_count=Count(
                "submissions", filter=Q(submissions__created_at__gte=thirty_days_ago)
            ),
        )
        .order_by("-response_count", "title")[:10]
    )

    task_status = {
        row["status"]: row["total"]
        for row in tasks.values("status").annotate(total=Count("id"))
    }

    return {
        "generated_at": now,
        "contacts": {
            "total": contacts.count(),
            "new_30_days": contacts.filter(created_at__gte=thirty_days_ago).count(),
            "email_opted_in": contacts.filter(email_consent_status="granted").count(),
            "members": members.filter(
                administrative_status=Member.AdministrativeStatus.ACTIVE
            ).count(),
        },
        "tasks": {
            "open": open_tasks.count(),
            "overdue": overdue_tasks.count(),
            "due_soon": due_soon_tasks.count(),
            "completed": completed_tasks.count(),
            "completion_rate": _percent(completed_tasks.count(), tasks.count()),
            "status": task_status,
        },
        "documents": {
            "total": Document.objects.for_site(site).count(),
            "new_30_days": Document.objects.for_site(site)
            .filter(created_at__gte=thirty_days_ago)
            .count(),
        },
        "forms": {
            "active": IntakeForm.objects.for_site(site).filter(is_active=True).count(),
            "submissions": submissions.count(),
            "submissions_30_days": submissions.filter(
                created_at__gte=thirty_days_ago
            ).count(),
            "signed_waivers": submissions.filter(agreed_at__isnull=False).count(),
            "performance": form_performance,
        },
        "volunteers": {
            "active": volunteers.filter(status=VolunteerProfile.Status.ACTIVE).count(),
            "total_hours": volunteer_hours,
            "hours_30_days": recent_volunteer_hours,
            "completed_assignments": VolunteerAssignment.objects.filter(
                shift__site=site, status=VolunteerAssignment.Status.COMPLETED
            ).count(),
            "no_shows": VolunteerAssignment.objects.filter(
                shift__site=site, status=VolunteerAssignment.Status.NO_SHOW
            ).count(),
        },
        "sponsors": {
            "active": Sponsor.objects.for_site(site)
            .filter(status=Sponsor.Status.ACTIVE)
            .count(),
            "prospects": Sponsor.objects.for_site(site)
            .filter(status=Sponsor.Status.PROSPECT)
            .count(),
            "committed_display": Decimal(committed_sponsorship_cents) / 100,
            "paid_display": Decimal(paid_sponsorship_cents) / 100,
        },
        "automations": {
            "active_rules": AutomationRule.objects.for_site(site)
            .filter(is_active=True)
            .count(),
            "runs_30_days": recent_runs.count(),
            "success_rate": _percent(successful_runs, recent_runs.count()),
            "failed_30_days": recent_runs.filter(
                status=AutomationRun.Status.FAILED
            ).count(),
        },
        "activity_30_days": Activity.objects.for_site(site)
        .filter(created_at__gte=thirty_days_ago)
        .count(),
        "monthly_contacts": monthly_contacts,
        "monthly_submissions": monthly_submissions,
        "today": today,
    }
