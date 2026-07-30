from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, SiteDeletionRequest, SupportAccessGrant


def record_audit_event(
    *,
    action,
    actor=None,
    site_id=None,
    target=None,
    summary=None,
    request=None,
):
    """Record a deliberate privileged/domain action without storing raw secrets."""
    target_type = ""
    target_id = ""
    if target is not None:
        target_type = target._meta.label_lower
        target_id = str(target.pk)

    return AuditEvent.objects.create(
        action=action,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        site_id=site_id,
        target_type=target_type,
        target_id=target_id,
        summary=summary or {},
        request_id=getattr(request, "request_id", "") if request else "",
        ip_address=request.META.get("REMOTE_ADDR") if request else None,
        user_agent=request.headers.get("User-Agent", "")[:512] if request else "",
    )


def grant_support_access(*, site, actor, reason, hours=1, request=None):
    if not reason.strip():
        raise ValidationError("A support-access reason is required.")
    grant = SupportAccessGrant.objects.create(
        site=site,
        site_name=site.display_name,
        granted_to=actor,
        reason=reason.strip(),
        expires_at=timezone.now() + timedelta(hours=max(1, min(hours, 8))),
    )
    record_audit_event(
        action="support.access_granted",
        actor=actor,
        site_id=site.id,
        target=grant,
        summary={"reason": reason[:200], "expires_at": grant.expires_at.isoformat()},
        request=request,
    )
    return grant


def active_support_grant(*, site, actor):
    return SupportAccessGrant.objects.filter(
        site=site,
        granted_to=actor,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()


def request_site_deletion(*, site, actor, reason, request=None):
    if not reason.strip():
        raise ValidationError("A deletion reason is required.")
    if site.status not in (
        site.Status.SUSPENDED,
        site.Status.CANCELED,
        site.Status.ARCHIVED,
    ):
        raise ValidationError("Suspend or archive the site before requesting deletion.")
    pending = SiteDeletionRequest.objects.filter(
        site=site,
        status__in=(
            SiteDeletionRequest.Status.REQUESTED,
            SiteDeletionRequest.Status.APPROVED,
        ),
    ).first()
    if pending:
        return pending
    deletion = SiteDeletionRequest.objects.create(
        site=site,
        site_id_snapshot=site.id,
        site_slug=site.slug,
        site_name=site.display_name,
        reason=reason.strip(),
        requested_by=actor,
    )
    record_audit_event(
        action="site.deletion_requested",
        actor=actor,
        site_id=site.id,
        target=deletion,
        summary={"reason": reason[:200]},
        request=request,
    )
    return deletion


@transaction.atomic
def approve_site_deletion(*, deletion, actor, request=None):
    deletion = (
        SiteDeletionRequest.objects.select_for_update(of=("self",))
        .select_related("site")
        .get(pk=deletion.pk)
    )
    if deletion.status != SiteDeletionRequest.Status.REQUESTED:
        raise ValidationError("Only a pending deletion can be approved.")
    if deletion.requested_by_id == actor.id:
        raise ValidationError(
            "A different platform administrator must approve deletion."
        )
    deletion.status = SiteDeletionRequest.Status.APPROVED
    deletion.approved_by = actor
    deletion.approved_at = timezone.now()
    deletion.deletion_eligible_at = timezone.now() + timedelta(
        days=settings.SUSPENDED_DATA_RETENTION_DAYS
    )
    deletion.save()
    record_audit_event(
        action="site.deletion_approved",
        actor=actor,
        site_id=deletion.site_id_snapshot,
        target=deletion,
        summary={"eligible_at": deletion.deletion_eligible_at.isoformat()},
        request=request,
    )
    return deletion


@transaction.atomic
def cancel_site_deletion(*, deletion, actor, reason, request=None):
    deletion = SiteDeletionRequest.objects.select_for_update().get(pk=deletion.pk)
    if deletion.status not in (
        SiteDeletionRequest.Status.REQUESTED,
        SiteDeletionRequest.Status.APPROVED,
    ):
        raise ValidationError("This deletion request can no longer be canceled.")
    if not reason.strip():
        raise ValidationError("A cancellation reason is required.")
    deletion.status = SiteDeletionRequest.Status.CANCELED
    deletion.save(update_fields=("status",))
    record_audit_event(
        action="site.deletion_canceled",
        actor=actor,
        site_id=deletion.site_id_snapshot,
        target=deletion,
        summary={"reason": reason[:200]},
        request=request,
    )
    return deletion


@transaction.atomic
def execute_site_deletion(*, deletion):
    deletion = (
        SiteDeletionRequest.objects.select_for_update(of=("self",))
        .select_related("site")
        .get(pk=deletion.pk)
    )
    if (
        deletion.status != SiteDeletionRequest.Status.APPROVED
        or deletion.deletion_eligible_at is None
        or deletion.deletion_eligible_at > timezone.now()
        or deletion.site is None
    ):
        raise ValidationError("This site is not eligible for deletion.")
    site = deletion.site
    record_audit_event(
        action="site.deletion_executed",
        site_id=deletion.site_id_snapshot,
        target=deletion,
        summary={"site_slug": deletion.site_slug},
    )
    # Financial and usage snapshots deliberately use PROTECT during normal
    # operation. Only this separately approved, retention-expired path removes
    # them in dependency order before the owning site is deleted.
    from communications.models import SmsUsageEvent
    from contacts.models import MemberSubscription
    from payments.models import (
        Dispute,
        FinancialTransition,
        InventoryHold,
        MembershipPayment,
        Order,
        OrderLine,
        Refund,
        Ticket,
    )

    FinancialTransition.objects.for_site(site).delete()
    Dispute.objects.for_site(site).delete()
    Refund.objects.for_site(site).delete()
    Ticket.objects.for_site(site).delete()
    InventoryHold.objects.for_site(site).delete()
    OrderLine.objects.filter(order__site=site).delete()
    Order.objects.for_site(site).delete()
    MembershipPayment.objects.for_site(site).delete()
    MemberSubscription.objects.for_site(site).delete()
    SmsUsageEvent.objects.for_site(site).delete()
    site.delete()
    deletion.site = None
    deletion.status = SiteDeletionRequest.Status.COMPLETED
    deletion.completed_at = timezone.now()
    deletion.save(update_fields=("site", "status", "completed_at"))
    return deletion
