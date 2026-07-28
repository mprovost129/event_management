import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from ops.tests.test_platform_operations import operations_fixture
from subscriptions.models import StripeWebhookEvent


@pytest.mark.django_db
def test_restore_verification_is_read_only_and_requires_explicit_copy_confirmation():
    operations_fixture()
    with pytest.raises(CommandError, match="isolated restored database"):
        call_command("post_restore_verify")

    output = io.StringIO()
    call_command("post_restore_verify", confirm_restored_copy=True, stdout=output)
    payload = json.loads(output.getvalue())

    assert payload["ok"] is True
    assert payload["counts"]["sites"] == 1
    assert payload["counts"]["users"] == 1


@pytest.mark.django_db
def test_pilot_readiness_requires_operable_site_contact_and_published_event():
    _, site, _ = operations_fixture()
    output = io.StringIO()
    with pytest.raises(CommandError, match="not ready"):
        call_command("pilot_readiness", site.slug, stdout=output)

    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    output = io.StringIO()
    call_command("pilot_readiness", site.slug, stdout=output)
    assert json.loads(output.getvalue())["ok"] is True


@pytest.mark.django_db
def test_alert_summary_fails_external_monitor_when_webhook_processing_failed():
    StripeWebhookEvent.objects.create(
        stripe_event_id="evt_launch_alert",
        event_type="customer.subscription.updated",
        status=StripeWebhookEvent.Status.FAILED,
        error="synthetic failure",
    )
    output = io.StringIO()

    with pytest.raises(CommandError, match="require attention"):
        call_command(
            "alert_summary",
            json=True,
            fail_on_alert=True,
            stdout=output,
        )

    payload = json.loads(output.getvalue())
    assert payload["ok"] is False
    assert payload["alerts"][0]["code"] == "platform_webhook_failed"
