import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site_id = models.UUIDField(null=True, blank=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    request_id = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=255, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("site_id", "-created_at"), name="ops_audit_site_created"
            ),
            models.Index(
                fields=("action", "-created_at"), name="ops_audit_action_created"
            ),
        ]

    def __str__(self):
        target = f" {self.target_type}:{self.target_id}" if self.target_type else ""
        return f"{self.action}{target}"


class SupportAccessGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(
        "sites.Site",
        null=True,
        on_delete=models.SET_NULL,
        related_name="support_access_grants",
    )
    site_name = models.CharField(max_length=160)
    granted_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_access_grants",
    )
    reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def is_active(self):
        return (
            self.site_id is not None
            and self.revoked_at is None
            and self.expires_at > timezone.now()
        )


class SiteDeletionRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Awaiting second approval"
        APPROVED = "approved", "Approved for retention countdown"
        CANCELED = "canceled", "Canceled"
        COMPLETED = "completed", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    site = models.ForeignKey(
        "sites.Site",
        null=True,
        on_delete=models.SET_NULL,
        related_name="deletion_requests",
    )
    site_id_snapshot = models.UUIDField()
    site_slug = models.SlugField(max_length=63)
    site_name = models.CharField(max_length=160)
    reason = models.CharField(max_length=500)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REQUESTED
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="site_deletions_requested",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="site_deletions_approved",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    deletion_eligible_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-requested_at",)


class SystemHeartbeat(models.Model):
    key = models.CharField(max_length=50, unique=True)
    observed_at = models.DateTimeField(default=timezone.now, db_index=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("key",)

    def __str__(self):
        return f"{self.key}: {self.observed_at}"
