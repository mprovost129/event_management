from .models import AuditEvent


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
