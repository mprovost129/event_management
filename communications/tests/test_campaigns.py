import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from communications.callbacks import process_provider_callback
from communications.campaigns import (
    CampaignUnavailable,
    SmsLimitExceeded,
    audience_contacts,
    campaign_metrics,
    campaign_preview,
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


def test_sms_segment_count_handles_gsm_extensions_and_unicode():
    assert sms_segment_count("a" * 160) == 1
    assert sms_segment_count("a" * 161) == 2
    assert sms_segment_count("€" * 80) == 1
    assert sms_segment_count("€" * 81) == 2
    assert sms_segment_count("🙂" * 70) == 1
    assert sms_segment_count("🙂" * 71) == 2


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
    assert 'data-campaign-editor' in content
    assert 'data-audience-section="tag"' in content
    assert "Save and review audience" in content
    assert "You will review the exact eligible audience" in content


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
