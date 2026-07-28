import uuid

from django.conf import settings
from django.db import models


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
