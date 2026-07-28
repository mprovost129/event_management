import pytest
from django.test import RequestFactory

from ops.models import AuditEvent
from ops.services import record_audit_event
from users.models import User


@pytest.mark.django_db
def test_record_audit_event_captures_bounded_request_context():
    actor = User.objects.create_user(
        email="owner@example.com", password="test-password"
    )
    request = RequestFactory().post("/admin/action")
    request.user = actor
    request.request_id = "request-12345678"
    request.META["REMOTE_ADDR"] = "127.0.0.1"
    request.META["HTTP_USER_AGENT"] = "test-agent"

    event = record_audit_event(
        action="site.role.changed",
        actor=actor,
        target=actor,
        summary={"role": "site_manager"},
        request=request,
    )

    stored = AuditEvent.objects.get(pk=event.pk)
    assert stored.actor == actor
    assert stored.request_id == "request-12345678"
    assert stored.target_type == "users.user"
    assert stored.summary == {"role": "site_manager"}
    assert stored.user_agent == "test-agent"
