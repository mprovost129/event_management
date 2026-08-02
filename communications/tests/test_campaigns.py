import base64
import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from communications.callbacks import process_provider_callback
from communications.campaigns import (
    CampaignUnavailable,
    SmsLimitExceeded,
    audience_contacts,
    campaign_metrics,
    campaign_preview,
    cancel_campaign,
    expand_campaign,
    launch_campaign,
    sms_segment_count,
    unsubscribe,
)
from communications.models import (
    Campaign,
    CampaignRecipient,
    OutboundMessage,
    ProviderCallbackEvent,
    SmsAllowance,
    SmsUsageEvent,
)
from communications.providers import provider_for
from communications.services import deliver_message, queued_message_ids
from contacts.models import (
    ConsentStatus,
    Contact,
    ContactTag,
    ContactTagAssignment,
    Member,
)
from content.models import BlogPost
from events.models import Event, EventOccurrence, Invitation, Registration
from sites.services import create_subscriber_site
from users.models import User


def campaign_fixture():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug="boot-scooters",
        timezone_name="America/New_York",
    )
    # Email campaigns fail closed without a postal address, so every fixture
    # that actually sends one needs it set.
    site.postal_address = "PO Box 44, Attleboro, MA 02703"
    site.save(update_fields=("postal_address", "updated_at"))
    return owner, site


def contact_for(site, number=1, *, email_consent=True, sms_consent=False):
    return Contact.objects.create(
        site=site,
        first_name=f"Dancer {number}",
        last_name="Tester",
        email=f"dancer{number}@example.com",
        phone=f"+1555000{number:04d}",
        email_consent_status=(
            ConsentStatus.GRANTED if email_consent else ConsentStatus.UNKNOWN
        ),
        sms_consent_status=(
            ConsentStatus.GRANTED if sms_consent else ConsentStatus.UNKNOWN
        ),
    )


def draft_campaign(site, **overrides):
    values = {
        "site": site,
        "name": "August newsletter",
        "channel": Campaign.Channel.EMAIL,
        "subject": "August dances",
        "body": "Here are this month's dances.",
        "audience": Campaign.Audience.ALL,
    }
    values.update(overrides)
    return Campaign.objects.create(**values)


@pytest.mark.django_db
def test_campaign_list_filters_without_per_campaign_metric_queries(client):
    owner, site = campaign_fixture()
    for number in range(10):
        draft_campaign(
            site,
            name=f"Newsletter {number}",
            status=(Campaign.Status.SENT if number == 0 else Campaign.Status.DRAFT),
        )
    draft_campaign(
        site,
        name="Volunteer text",
        channel=Campaign.Channel.SMS,
        subject="",
    )
    client.force_login(owner)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("communications:campaign_list", args=(site.id,)))
    filtered = client.get(
        reverse("communications:campaign_list", args=(site.id,)),
        {"q": "Newsletter 0", "status": "sent", "channel": "email"},
    )

    assert response.status_code == filtered.status_code == 200
    assert len(queries) < 20
    assert "Newsletter 0" in filtered.content.decode()
    assert "Newsletter 1" not in filtered.content.decode()
    assert "Volunteer text" not in filtered.content.decode()


def test_sms_segment_count_handles_gsm_extensions_and_unicode():
    assert sms_segment_count("a" * 160) == 1
    assert sms_segment_count("a" * 161) == 2
    assert sms_segment_count("€" * 80) == 1
    assert sms_segment_count("€" * 81) == 2
    # Emoji are billed in UCS-2 code units, not Unicode codepoints: most sit
    # outside the Basic Multilingual Plane and need a surrogate pair (2
    # units) apiece, so the 70-unit single-segment cap is 35 emoji, not 70.
    assert sms_segment_count("🙂" * 35) == 1
    assert sms_segment_count("🙂" * 36) == 2
    assert sms_segment_count("🙂" * 70) == 3


@pytest.mark.django_db
def test_email_campaign_excludes_contacts_without_consent_and_delivers():
    owner, site = campaign_fixture()
    eligible = contact_for(site, 1, email_consent=True)
    excluded = contact_for(site, 2, email_consent=False)
    campaign = draft_campaign(site)

    preview = campaign_preview(campaign)
    assert preview["candidate_count"] == 2
    assert preview["eligible_count"] == 1
    assert preview["excluded_reasons"] == {"No marketing email consent": 1}

    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)

    message = OutboundMessage.objects.get(contact=eligible)
    excluded_recipient = CampaignRecipient.objects.get(contact=excluded)
    assert message.unsubscribe_url in message.body
    assert excluded_recipient.status == CampaignRecipient.Status.EXCLUDED
    assert OutboundMessage.objects.filter(contact=excluded).count() == 0

    deliver_message(message.id)
    message.refresh_from_db()
    campaign.refresh_from_db()
    assert message.status == OutboundMessage.Status.SENT
    assert message.body == ""
    assert message.unsubscribe_url == ""
    assert campaign.status == Campaign.Status.SENT
    assert len(mail.outbox) == 1
    assert "List-Unsubscribe" in mail.outbox[0].extra_headers


@pytest.mark.django_db
def test_unsubscribe_immediately_blocks_queued_marketing():
    owner, site = campaign_fixture()
    contact = contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    message = OutboundMessage.objects.get(campaign=campaign)
    token = message.unsubscribe_url.rstrip("/").rsplit("/", 1)[-1]

    capability = unsubscribe(site=site, token=token)
    deliver_message(message.id)

    contact.refresh_from_db()
    message.refresh_from_db()
    campaign.refresh_from_db()
    assert capability is not None
    assert contact.email_consent_status == ConsentStatus.WITHDRAWN
    assert message.status == OutboundMessage.Status.UNSUBSCRIBED
    assert message.body == ""
    assert campaign.status == Campaign.Status.SENT
    assert mail.outbox == []


@pytest.mark.django_db
def test_repeat_unsubscribe_click_shows_the_completed_page_not_a_dead_end(client):
    owner, site = campaign_fixture()
    contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    message = OutboundMessage.objects.get(campaign=campaign)
    token = message.unsubscribe_url.rstrip("/").rsplit("/", 1)[-1]
    url = reverse("communications:unsubscribe", kwargs={"token": token})

    first_get = client.get(url, headers={"host": f"{site.slug}.localhost"})
    first_post = client.post(url, headers={"host": f"{site.slug}.localhost"})
    # A second visit after the link was already used - by that first POST,
    # or by a mail client's one-click List-Unsubscribe-Post firing on its
    # own - must not dead-end.
    second_get = client.get(url, headers={"host": f"{site.slug}.localhost"})
    second_post = client.post(url, headers={"host": f"{site.slug}.localhost"})

    assert first_get.status_code == 200
    assert "Stop marketing messages" in first_get.content.decode()
    assert first_post.status_code == 200
    assert "You have been unsubscribed" in first_post.content.decode()
    assert second_get.status_code == 200
    assert "You have been unsubscribed" in second_get.content.decode()
    assert second_post.status_code == 200
    assert "You have been unsubscribed" in second_post.content.decode()


@pytest.mark.django_db
def test_unknown_unsubscribe_token_still_404s(client):
    _, site = campaign_fixture()

    response = client.get(
        reverse("communications:unsubscribe", kwargs={"token": "not-a-real-token"}),
        headers={"host": f"{site.slug}.localhost"},
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_consent_is_rechecked_immediately_before_delivery():
    owner, site = campaign_fixture()
    contact = contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    message = OutboundMessage.objects.get(campaign=campaign)
    contact.email_consent_status = ConsentStatus.WITHDRAWN
    contact.save(update_fields=("email_consent_status", "updated_at"))

    deliver_message(message.id)

    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.SUPPRESSED
    assert message.body == ""
    assert mail.outbox == []


@pytest.mark.django_db
def test_canceling_a_draft_campaign_marks_it_canceled():
    owner, site = campaign_fixture()
    campaign = draft_campaign(site)

    canceled = cancel_campaign(campaign=campaign, actor=owner)

    assert canceled.status == Campaign.Status.CANCELED
    assert canceled.completed_at is not None


@pytest.mark.django_db
def test_canceling_a_scheduled_campaign_stops_it_from_ever_expanding():
    owner, site = campaign_fixture()
    contact_for(site, email_consent=True)
    campaign = draft_campaign(
        site, scheduled_for=timezone.now() + timedelta(days=1)
    )
    launch_campaign(campaign=campaign, actor=owner)
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.SCHEDULED

    cancel_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.CANCELED
    assert OutboundMessage.objects.filter(campaign=campaign).count() == 0


@pytest.mark.django_db
def test_canceling_a_sending_campaign_suppresses_unsent_messages_but_keeps_sent_ones():
    owner, site = campaign_fixture()
    sent_contact = contact_for(site, 1, email_consent=True)
    queued_contact = contact_for(site, 2, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    sent_message = OutboundMessage.objects.get(contact=sent_contact)
    queued_message = OutboundMessage.objects.get(contact=queued_contact)
    deliver_message(sent_message.id)

    cancel_campaign(campaign=campaign, actor=owner)

    campaign.refresh_from_db()
    sent_message.refresh_from_db()
    queued_message.refresh_from_db()
    assert campaign.status == Campaign.Status.CANCELED
    assert sent_message.status == OutboundMessage.Status.SENT
    assert queued_message.status == OutboundMessage.Status.SUPPRESSED
    assert queued_message.body == ""
    assert (
        CampaignRecipient.objects.get(outbound_message=queued_message).status
        == CampaignRecipient.Status.SUPPRESSED
    )
    assert (
        CampaignRecipient.objects.get(outbound_message=sent_message).status
        == CampaignRecipient.Status.SENT
    )
    # A no-op: the message is already terminal, so canceling must not resurrect it.
    deliver_message(queued_message.id)
    assert len(mail.outbox) == 1


@pytest.mark.django_db
@override_settings(SMS_DELIVERY_BACKEND="console", SMS_MONTHLY_SEGMENT_LIMIT=10)
def test_canceling_an_sms_campaign_releases_its_unused_reserved_segments():
    owner, site = campaign_fixture()
    contact_for(site, sms_consent=True)
    campaign = draft_campaign(
        site,
        channel=Campaign.Channel.SMS,
        subject="",
        body="Dance moved to 7 PM.",
    )
    launch_campaign(campaign=campaign, actor=owner, usage_confirmed=True)
    campaign.refresh_from_db()
    reserved_before_cancel = campaign.sms_reserved_segments
    assert reserved_before_cancel > 0

    cancel_campaign(campaign=campaign, actor=owner)

    campaign.refresh_from_db()
    allowance = SmsAllowance.objects.get(site=site)
    assert campaign.sms_reserved_segments == 0
    assert allowance.reserved_segments == 0


@pytest.mark.django_db
def test_cancel_campaign_rejects_a_campaign_that_already_finished():
    owner, site = campaign_fixture()
    contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    deliver_message(OutboundMessage.objects.get(campaign=campaign).id)
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.SENT

    with pytest.raises(CampaignUnavailable):
        cancel_campaign(campaign=campaign, actor=owner)


@pytest.mark.django_db
def test_campaign_cancel_view_requires_staff_and_redirects_with_a_message():
    owner, site = campaign_fixture()
    contact_for(site, email_consent=True)
    campaign = draft_campaign(
        site, scheduled_for=timezone.now() + timedelta(days=1)
    )
    launch_campaign(campaign=campaign, actor=owner)
    client = Client()
    client.force_login(owner)

    response = client.post(
        reverse(
            "communications:campaign_cancel",
            kwargs={"site_id": site.id, "campaign_id": campaign.id},
        )
    )

    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.CANCELED
    preview = client.get(response.url)
    assert "Campaign canceled" in preview.content.decode()


@pytest.mark.django_db
def test_all_member_nonmember_and_tag_audiences_are_site_scoped():
    _, site = campaign_fixture()
    member_contact = contact_for(site, 1)
    tagged_contact = contact_for(site, 2)
    nonmember_contact = contact_for(site, 3)
    Member.objects.create(site=site, contact=member_contact)
    tag = ContactTag.objects.create(site=site, name="Volunteers", slug="volunteers")
    ContactTagAssignment.objects.create(contact=tagged_contact, tag=tag)

    members = draft_campaign(site, audience=Campaign.Audience.MEMBERS)
    nonmembers = draft_campaign(site, audience=Campaign.Audience.NON_MEMBERS)
    tagged = draft_campaign(site, audience=Campaign.Audience.TAG, audience_tag=tag)

    assert list(audience_contacts(members)) == [member_contact]
    assert set(audience_contacts(nonmembers)) == {tagged_contact, nonmember_contact}
    assert list(audience_contacts(tagged)) == [tagged_contact]


@pytest.mark.django_db
def test_event_invitee_and_response_audiences_select_the_expected_contacts():
    _, site = campaign_fixture()
    invited_contact = contact_for(site, 1)
    going_contact = contact_for(site, 2)
    unrelated_contact = contact_for(site, 3)
    event = Event.objects.create(
        site=site,
        title="Friday dance",
        slug="friday-dance",
        status=Event.Status.PUBLISHED,
    )
    starts_at = timezone.now() + timedelta(days=7)
    occurrence = EventOccurrence.objects.create(
        site=site,
        event=event,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        timezone=site.timezone,
    )
    Invitation.objects.create(
        site=site,
        occurrence=occurrence,
        contact=invited_contact,
        token_hash="invitation-token-hash",
        expires_at=starts_at,
    )
    Registration.objects.create(
        site=site,
        occurrence=occurrence,
        contact=going_contact,
        response=Registration.Response.GOING,
        source=Registration.Source.MANAGER,
    )
    invitees = draft_campaign(
        site,
        audience=Campaign.Audience.EVENT_INVITEES,
        audience_occurrence=occurrence,
    )
    going = draft_campaign(
        site,
        audience=Campaign.Audience.RESPONSE,
        audience_occurrence=occurrence,
        response_filter=Registration.Response.GOING,
    )

    assert list(audience_contacts(invitees)) == [invited_contact]
    assert list(audience_contacts(going)) == [going_contact]
    assert unrelated_contact not in audience_contacts(invitees)


@pytest.mark.django_db
@override_settings(SMS_DELIVERY_BACKEND="console", SMS_MONTHLY_SEGMENT_LIMIT=10)
def test_sms_requires_confirmation_and_consumes_reserved_allowance():
    owner, site = campaign_fixture()
    contact_for(site, sms_consent=True)
    campaign = draft_campaign(
        site,
        channel=Campaign.Channel.SMS,
        subject="",
        body="Dance moved to 7 PM.",
    )

    with pytest.raises(CampaignUnavailable, match="Confirm"):
        launch_campaign(campaign=campaign, actor=owner)

    launch_campaign(campaign=campaign, actor=owner, usage_confirmed=True)
    campaign.refresh_from_db()
    assert campaign.sms_reserved_segments > 0
    expand_campaign(campaign.id)
    message = OutboundMessage.objects.get(campaign=campaign)
    deliver_message(message.id)

    allowance = SmsAllowance.objects.get(site=site)
    campaign.refresh_from_db()
    assert allowance.reserved_segments == 0
    assert allowance.sent_segments == message.sms_segments
    assert campaign.sms_reserved_segments == 0
    assert SmsUsageEvent.objects.filter(
        campaign=campaign, action=SmsUsageEvent.Action.ACCEPTED
    ).exists()


@pytest.mark.django_db
@override_settings(SMS_DELIVERY_BACKEND="console", SMS_MONTHLY_SEGMENT_LIMIT=1)
def test_sms_allowance_stops_campaign_before_queueing():
    owner, site = campaign_fixture()
    contact_for(site, sms_consent=True)
    campaign = draft_campaign(
        site,
        channel=Campaign.Channel.SMS,
        subject="",
        body="This is a long update. " * 30,
    )

    with pytest.raises(SmsLimitExceeded):
        launch_campaign(campaign=campaign, actor=owner, usage_confirmed=True)

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.DRAFT
    assert OutboundMessage.objects.count() == 0


@pytest.mark.django_db
def test_provider_callbacks_are_idempotent_and_terminal_statuses_do_not_regress():
    owner, site = campaign_fixture()
    contact = contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    message = OutboundMessage.objects.get(campaign=campaign)
    deliver_message(message.id)
    message.refresh_from_db()

    for event_type in ("delivered", "opened", "clicked", "bounced"):
        process_provider_callback(
            provider=message.provider,
            provider_event_id=f"evt-{event_type}",
            provider_message_id=message.provider_message_id,
            event_type=event_type,
        )
    process_provider_callback(
        provider=message.provider,
        provider_event_id="evt-bounced",
        provider_message_id=message.provider_message_id,
        event_type="bounced",
    )
    process_provider_callback(
        provider=message.provider,
        provider_event_id="evt-late-open",
        provider_message_id=message.provider_message_id,
        event_type="opened",
    )

    message.refresh_from_db()
    contact.refresh_from_db()
    assert message.status == OutboundMessage.Status.BOUNCED
    assert message.opened_at is not None
    assert message.clicked_at is not None
    assert contact.email_consent_status == ConsentStatus.SUPPRESSED
    assert ProviderCallbackEvent.objects.count() == 5
    metrics = campaign_metrics(campaign)
    assert metrics["sent"] == 1
    assert metrics["delivered"] == 1
    assert metrics["opened"] == 1
    assert metrics["clicked"] == 1


@pytest.mark.django_db
@override_settings(COMMUNICATIONS_WEBHOOK_SECRET="callback-secret")
def test_callback_endpoint_verifies_signature():
    payload = json.dumps(
        {"event_id": "evt-1", "message_id": "missing", "event_type": "delivered"}
    ).encode()
    signature = hmac.new(b"callback-secret", payload, hashlib.sha256).hexdigest()
    url = reverse("communications:provider_callback", kwargs={"provider": "django"})
    client = Client()

    assert (
        client.post(url, data=payload, content_type="application/json").status_code
        == 400
    )
    response = client.post(
        url,
        data=payload,
        content_type="application/json",
        headers={"X-Communications-Signature": signature},
    )
    assert response.status_code == 200
    assert (
        ProviderCallbackEvent.objects.get().status
        == ProviderCallbackEvent.Status.IGNORED
    )


@pytest.mark.django_db
@override_settings(
    EMAIL_DELIVERY_BACKEND="resend",
    RESEND_API_KEY="re_test_key",
    DEFAULT_FROM_EMAIL="Gather HQs <events@gatherhqs.com>",
)
@patch("communications.providers.resend.Emails.send")
def test_resend_provider_returns_provider_id_and_preserves_unsubscribe_headers(send):
    _, site = campaign_fixture()
    contact = contact_for(site, email_consent=True)
    message = OutboundMessage.objects.create(
        site=site,
        contact=contact,
        kind=OutboundMessage.Kind.CAMPAIGN,
        channel=OutboundMessage.Channel.EMAIL,
        recipient_email=contact.email,
        subject="Friday dance",
        body="Join us this Friday.",
        html_body="<h1>Join us this Friday.</h1>",
        is_marketing=True,
        unsubscribe_url="https://boot-scooters.gatherhqs.com/unsubscribe/example/",
    )
    send.return_value = {"id": "email_resend_123"}

    result = provider_for("email").send(message)

    assert result.provider == "resend"
    assert result.message_id == "email_resend_123"
    params, options = send.call_args.args
    assert params["from"] == "Gather HQs <events@gatherhqs.com>"
    assert params["to"] == [contact.email]
    assert params["headers"]["List-Unsubscribe"] == (
        "<https://boot-scooters.gatherhqs.com/unsubscribe/example/>"
    )
    assert params["headers"]["X-Gather-HQs-Message-ID"] == str(message.id)
    assert params["html"] == "<h1>Join us this Friday.</h1>"
    assert options == {"idempotency_key": f"gather-hqs-message-{message.id}"}


@pytest.mark.django_db
def test_resend_callback_verifies_svix_signature_and_suppresses_complaints(
    client,
    settings,
):
    _, site = campaign_fixture()
    contact = contact_for(site, email_consent=True)
    message = OutboundMessage.objects.create(
        site=site,
        contact=contact,
        kind=OutboundMessage.Kind.INVITATION,
        channel=OutboundMessage.Channel.EMAIL,
        recipient_email=contact.email,
        subject="Friday dance",
        body="You are invited.",
        status=OutboundMessage.Status.SENT,
        provider="resend",
        provider_message_id="email_resend_123",
    )
    secret_bytes = b"gather-hqs-resend-test-secret"
    settings.RESEND_WEBHOOK_SECRET = "whsec_" + base64.b64encode(secret_bytes).decode()
    url = reverse("communications:provider_callback", kwargs={"provider": "resend"})

    def signed_post(event_type, webhook_id):
        payload = json.dumps(
            {
                "type": event_type,
                "created_at": timezone.now().isoformat(),
                "data": {"email_id": message.provider_message_id},
            },
            separators=(",", ":"),
        ).encode()
        timestamp = str(int(timezone.now().timestamp()))
        signed = f"{webhook_id}.{timestamp}.{payload.decode()}".encode()
        signature = base64.b64encode(
            hmac.new(secret_bytes, signed, hashlib.sha256).digest()
        ).decode()
        return client.post(
            url,
            data=payload,
            content_type="application/json",
            headers={
                "Svix-Id": webhook_id,
                "Svix-Timestamp": timestamp,
                "Svix-Signature": f"v1,{signature}",
            },
        )

    assert signed_post("email.delivered", "resend-event-delivered").status_code == 200
    message.refresh_from_db()
    assert message.status == OutboundMessage.Status.DELIVERED
    assert message.delivered_at is not None

    assert signed_post("email.complained", "resend-event-complained").status_code == 200
    message.refresh_from_db()
    contact.refresh_from_db()
    assert message.status == OutboundMessage.Status.BOUNCED
    assert contact.email_consent_status == ConsentStatus.SUPPRESSED
    assert ProviderCallbackEvent.objects.filter(provider="resend").count() == 2

    assert (
        client.post(url, data=b"{}", content_type="application/json").status_code == 400
    )


@pytest.mark.django_db
def test_callback_processing_failure_is_durable_and_retryable():
    owner, site = campaign_fixture()
    contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)
    message = OutboundMessage.objects.get(campaign=campaign)
    deliver_message(message.id)
    message.refresh_from_db()

    callback_values = {
        "provider": message.provider,
        "provider_event_id": "evt-retryable",
        "provider_message_id": message.provider_message_id,
        "event_type": "delivered",
    }
    with pytest.raises(ValueError):
        process_provider_callback(**callback_values, occurred_at="not-a-date")
    assert (
        ProviderCallbackEvent.objects.get(provider_event_id="evt-retryable").status
        == ProviderCallbackEvent.Status.FAILED
    )

    process_provider_callback(**callback_values, occurred_at=timezone.now().isoformat())
    assert (
        ProviderCallbackEvent.objects.get(provider_event_id="evt-retryable").status
        == ProviderCallbackEvent.Status.PROCESSED
    )


@pytest.mark.django_db
def test_large_campaign_is_expanded_to_outbox_and_delivery_is_batched():
    owner, site = campaign_fixture()
    Contact.objects.bulk_create(
        [
            Contact(
                site=site,
                first_name=f"Dancer {number}",
                last_name="Batch",
                email=f"batch{number}@example.com",
                normalized_email=f"batch{number}@example.com",
                email_consent_status=ConsentStatus.GRANTED,
            )
            for number in range(205)
        ]
    )
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)

    assert OutboundMessage.objects.filter(campaign=campaign).count() == 205
    assert len(queued_message_ids(limit=100)) == 100


@pytest.mark.django_db
def test_blog_post_can_seed_campaign_and_campaign_can_be_duplicated():
    owner, site = campaign_fixture()
    post = BlogPost.objects.create(
        site=site,
        title="Festival recap",
        slug="festival-recap",
        body="We had a wonderful turnout.",
        author=owner,
    )
    client = Client()
    client.force_login(owner)
    create_url = reverse("communications:campaign_create", kwargs={"site_id": site.id})

    response = client.get(create_url, {"blog_post": post.id})
    assert response.status_code == 200
    assert response.context["form"].initial["subject"] == post.title

    response = client.post(
        create_url,
        {
            "name": "Festival newsletter",
            "channel": Campaign.Channel.EMAIL,
            "subject": post.title,
            "body": post.body,
            "audience": Campaign.Audience.ALL,
            "response_filter": "",
            "scheduled_for": "",
            "source_blog_post": str(post.id),
        },
    )
    campaign = Campaign.objects.get(name="Festival newsletter")
    assert response.status_code == 302
    assert campaign.source_blog_post == post

    duplicate_url = reverse(
        "communications:campaign_duplicate",
        kwargs={"site_id": site.id, "campaign_id": campaign.id},
    )
    assert client.post(duplicate_url).status_code == 302
    duplicate = Campaign.objects.get(duplicated_from=campaign)
    assert duplicate.status == Campaign.Status.DRAFT
    assert duplicate.body == campaign.body


@pytest.mark.django_db
def test_campaign_composer_keeps_source_post_after_validation_error():
    owner, site = campaign_fixture()
    post = BlogPost.objects.create(
        site=site,
        title="Festival recap",
        slug="festival-recap",
        body="We had a wonderful turnout.",
        author=owner,
    )
    client = Client()
    client.force_login(owner)
    create_url = reverse("communications:campaign_create", kwargs={"site_id": site.id})

    response = client.post(
        create_url,
        {
            "name": "Festival newsletter",
            "channel": Campaign.Channel.EMAIL,
            "subject": "",
            "body": post.body,
            "audience": Campaign.Audience.ALL,
            "source_blog_post": str(post.id),
        },
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert response.context["source_post"] == post
    assert f'value="{post.id}"' in content
    assert "independent copy" in content
    assert "Nothing sends from this screen" in content


@pytest.mark.django_db
def test_campaign_composer_renders_guided_audience_controls():
    owner, site = campaign_fixture()
    client = Client()
    client.force_login(owner)

    response = client.get(
        reverse("communications:campaign_create", kwargs={"site_id": site.id})
    )
    content = response.content.decode()

    assert response.status_code == 200
    assert "data-campaign-editor" in content
    assert 'data-audience-section="tag"' in content
    assert "Save and review audience" in content
    assert "You will review the exact eligible audience" in content


@pytest.mark.django_db
def test_campaign_actions_use_plain_delivery_language(client):
    owner, site = campaign_fixture()
    contact_for(site, email_consent=True)
    campaign = draft_campaign(site)
    client.force_login(owner)
    preview_url = reverse(
        "communications:campaign_preview",
        kwargs={"site_id": site.id, "campaign_id": campaign.id},
    )

    preview = client.get(preview_url)
    test_response = client.post(
        preview_url,
        {"action": "test", "test-email": "owner@example.com"},
        follow=True,
    )
    launch_response = client.post(
        preview_url,
        {"action": "launch"},
        follow=True,
    )

    assert preview.status_code == 200
    assert "Send campaign" in preview.content.decode()
    assert "Queue campaign" not in preview.content.decode()
    assert "Test message is being sent." in test_response.content.decode()
    assert "Campaign delivery is starting." in launch_response.content.decode()


@pytest.mark.django_db
@override_settings(SMS_DELIVERY_BACKEND="disabled")
def test_sms_fails_closed_when_no_provider_is_configured():
    owner, site = campaign_fixture()
    contact_for(site, sms_consent=True)
    campaign = draft_campaign(
        site, channel=Campaign.Channel.SMS, subject="", body="Dance update"
    )

    with pytest.raises(ValidationError, match="not configured"):
        launch_campaign(campaign=campaign, actor=owner, usage_confirmed=True)


@pytest.mark.django_db
def test_email_campaign_is_blocked_until_a_postal_address_is_set():
    owner, site = campaign_fixture()
    contact_for(site, 1, email_consent=True)
    campaign = draft_campaign(site)
    site.postal_address = ""
    site.save(update_fields=("postal_address", "updated_at"))

    with pytest.raises(CampaignUnavailable) as blocked:
        launch_campaign(campaign=campaign, actor=owner)

    campaign.refresh_from_db()
    assert "mailing address" in str(blocked.value)
    assert campaign.status == Campaign.Status.DRAFT


@pytest.mark.django_db
def test_marketing_email_carries_the_sender_name_and_postal_address():
    owner, site = campaign_fixture()
    recipient = contact_for(site, 1, email_consent=True)
    campaign = draft_campaign(site)

    launch_campaign(campaign=campaign, actor=owner)
    expand_campaign(campaign.id)

    body = OutboundMessage.objects.get(contact=recipient).body
    assert "Boot Scooters" in body
    assert "PO Box 44, Attleboro, MA 02703" in body
    assert "Unsubscribe:" in body


@pytest.mark.django_db
@override_settings(SMS_DELIVERY_BACKEND="console", SMS_MONTHLY_SEGMENT_LIMIT=10)
def test_sms_campaign_does_not_require_a_postal_address():
    owner, site = campaign_fixture()
    site.postal_address = ""
    site.save(update_fields=("postal_address", "updated_at"))
    contact_for(site, 1, email_consent=False, sms_consent=True)
    campaign = draft_campaign(
        site,
        channel=Campaign.Channel.SMS,
        subject="",
        body="Dance moved to 7 PM.",
    )

    # The requirement is specific to commercial email, not SMS.
    launch_campaign(campaign=campaign, actor=owner, usage_confirmed=True)

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.SCHEDULED


@pytest.mark.django_db
def test_campaign_scheduled_before_the_address_rule_fails_visibly_instead_of_sending():
    owner, site = campaign_fixture()
    contact_for(site, 1, email_consent=True)
    campaign = draft_campaign(site)
    launch_campaign(campaign=campaign, actor=owner)
    # Stand in for a campaign that reached SCHEDULED before the rule existed.
    site.postal_address = ""
    site.save(update_fields=("postal_address", "updated_at"))

    expand_campaign(campaign.id)

    campaign.refresh_from_db()
    assert campaign.status == Campaign.Status.FAILED
    assert "mailing address" in campaign.last_error
    # Nothing reached the outbox, so no non-compliant mail was queued.
    assert OutboundMessage.objects.filter(campaign=campaign).count() == 0


@pytest.mark.django_db
def test_campaign_review_warns_about_the_missing_address_before_launch(client):
    owner, site = campaign_fixture()
    contact_for(site, 1, email_consent=True)
    campaign = draft_campaign(site)
    site.postal_address = ""
    site.save(update_fields=("postal_address", "updated_at"))
    client.force_login(owner)
    url = reverse("communications:campaign_preview", args=(site.id, campaign.id))

    warned = client.get(url).content.decode()

    site.postal_address = "PO Box 44, Attleboro, MA 02703"
    site.save(update_fields=("postal_address", "updated_at"))
    settled = client.get(url).content.decode()

    assert "Add mailing address" in warned
    assert "Add mailing address" not in settled
