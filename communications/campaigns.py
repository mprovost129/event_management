import hashlib
import math
import secrets
from collections import Counter

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from contacts.models import ConsentRecord, ConsentStatus, Contact

from .models import (
    Campaign,
    CampaignRecipient,
    OutboundMessage,
    SmsAllowance,
    SmsUsageEvent,
    UnsubscribeCapability,
)
from .providers import channel_is_configured

GSM_BASIC = set(
    "@\u00a3$\u00a5\u00e8\u00e9\u00f9\u00ec\u00f2\u00c7\n\u00d8\u00f8\r"
    "\u00c5\u00e5\u0394_\u03a6\u0393\u039b\u03a9\u03a0\u03a8\u03a3\u0398\u039e"
    "\u001b\u00c6\u00e6\u00df\u00c9 !\"#\u00a4%&'()*+,-./0123456789:;<=>?"
    "\u00a1ABCDEFGHIJKLMNOPQRSTUVWXYZ\u00c4\u00d6\u00d1\u00dc\u00a7\u00bf"
    "abcdefghijklmnopqrstuvwxyz\u00e4\u00f6\u00f1\u00fc\u00e0"
)
GSM_EXTENDED = set("^{}\\[~]|\u20ac\f")
UNSUBSCRIBE_TOKEN_LENGTH = 43


class CampaignUnavailable(ValidationError):
    pass


class SmsLimitExceeded(ValidationError):
    pass


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sms_segment_count(body):
    gsm_units = 0
    for character in body:
        if character in GSM_BASIC:
            gsm_units += 1
        elif character in GSM_EXTENDED:
            gsm_units += 2
        else:
            return 1 if len(body) <= 70 else math.ceil(len(body) / 67)
    return 1 if gsm_units <= 160 else math.ceil(gsm_units / 153)


def audience_contacts(campaign):
    contacts = Contact.objects.for_site(campaign.site).filter(archived_at__isnull=True)
    if campaign.audience == Campaign.Audience.MEMBERS:
        contacts = contacts.filter(membership__administrative_status="active")
    elif campaign.audience == Campaign.Audience.NON_MEMBERS:
        contacts = contacts.filter(membership__isnull=True)
    elif campaign.audience == Campaign.Audience.EVENT_INVITEES:
        contacts = contacts.filter(
            event_invitations__occurrence=campaign.audience_occurrence
        )
    elif campaign.audience == Campaign.Audience.RESPONSE:
        contacts = contacts.filter(
            event_registrations__occurrence=campaign.audience_occurrence,
            event_registrations__response=campaign.response_filter,
        )
    elif campaign.audience == Campaign.Audience.TAG:
        contacts = contacts.filter(tags=campaign.audience_tag)
    return contacts.distinct().order_by("id")


def contact_eligibility(contact, channel):
    if contact.archived_at is not None:
        return False, "Contact is archived"
    if channel == Campaign.Channel.EMAIL:
        if not contact.email:
            return False, "No email address"
        if contact.email_consent_status == ConsentStatus.SUPPRESSED:
            return False, "Email is suppressed"
        if contact.email_consent_status != ConsentStatus.GRANTED:
            return False, "No marketing email consent"
        return True, ""
    if not contact.phone:
        return False, "No phone number"
    if contact.sms_consent_status == ConsentStatus.SUPPRESSED:
        return False, "SMS is suppressed"
    if contact.sms_consent_status != ConsentStatus.GRANTED:
        return False, "No SMS consent"
    return True, ""


def _unsubscribe_url_length(campaign):
    hostname = campaign.site.domains.get(is_canonical=True).hostname
    path = reverse(
        "communications:unsubscribe", kwargs={"token": "x" * UNSUBSCRIBE_TOKEN_LENGTH}
    )
    return len(f"https://{hostname}{path}")


def sms_body_for_estimate(campaign):
    placeholder_url = "x" * _unsubscribe_url_length(campaign)
    return f"{campaign.body.rstrip()}\n\nStop messages: {placeholder_url}"


def campaign_preview(campaign):
    reasons = Counter()
    eligible = 0
    candidates = 0
    segments = 0
    sms_segments = (
        sms_segment_count(sms_body_for_estimate(campaign))
        if campaign.channel == Campaign.Channel.SMS
        else 0
    )
    for contact in audience_contacts(campaign).iterator(chunk_size=500):
        candidates += 1
        allowed, reason = contact_eligibility(contact, campaign.channel)
        if allowed:
            eligible += 1
            segments += sms_segments
        else:
            reasons[reason] += 1
    allowance = current_sms_allowance(campaign.site, create=False)
    return {
        "candidate_count": candidates,
        "eligible_count": eligible,
        "excluded_count": candidates - eligible,
        "excluded_reasons": dict(reasons),
        "estimated_segments": segments,
        "segments_per_message": sms_segments,
        "sms_configured": channel_is_configured(Campaign.Channel.SMS),
        "sms_remaining": allowance.remaining_segments if allowance else 0,
    }


def current_sms_allowance(site, *, create=True):
    period_start = timezone.localdate().replace(day=1)
    if not create:
        return SmsAllowance.objects.filter(site=site, period_start=period_start).first()
    allowance, _ = SmsAllowance.objects.get_or_create(
        site=site,
        period_start=period_start,
        defaults={"included_segments": settings.SMS_MONTHLY_SEGMENT_LIMIT},
    )
    return allowance


@transaction.atomic
def launch_campaign(*, campaign, actor, usage_confirmed=False):
    campaign = (
        Campaign.objects.select_for_update().select_related("site").get(pk=campaign.pk)
    )
    if campaign.status != Campaign.Status.DRAFT:
        raise CampaignUnavailable("Only a draft campaign can be launched.")
    campaign.full_clean()
    preview = campaign_preview(campaign)
    if preview["eligible_count"] == 0:
        raise CampaignUnavailable("This audience has no eligible recipients.")
    if not channel_is_configured(campaign.channel):
        raise CampaignUnavailable(
            f"{campaign.get_channel_display()} delivery is not configured."
        )
    if campaign.channel == Campaign.Channel.SMS:
        if not usage_confirmed:
            raise CampaignUnavailable("Confirm the estimated SMS usage before sending.")
        allowance = SmsAllowance.objects.select_for_update().get(
            pk=current_sms_allowance(campaign.site).pk
        )
        if preview["estimated_segments"] > allowance.remaining_segments:
            raise SmsLimitExceeded(
                "This campaign exceeds the site's available SMS segments."
            )
        allowance.reserved_segments += preview["estimated_segments"]
        allowance.save(update_fields=("reserved_segments", "updated_at"))
        campaign.sms_allowance = allowance
        campaign.sms_reserved_segments = preview["estimated_segments"]
        campaign.usage_confirmed_at = timezone.now()
        SmsUsageEvent.objects.create(
            site=campaign.site,
            campaign=campaign,
            allowance=allowance,
            action=SmsUsageEvent.Action.RESERVED,
            segments=preview["estimated_segments"],
        )
    campaign.recipient_count = preview["candidate_count"]
    campaign.eligible_count = preview["eligible_count"]
    campaign.excluded_count = preview["excluded_count"]
    campaign.estimated_segments = preview["estimated_segments"]
    campaign.status = Campaign.Status.SCHEDULED
    campaign.scheduled_for = campaign.scheduled_for or timezone.now()
    campaign.last_error = ""
    campaign.save()
    if campaign.scheduled_for <= timezone.now():
        transaction.on_commit(lambda: _dispatch_campaign(campaign.id))
    return campaign


def _dispatch_campaign(campaign_id):
    from .tasks import expand_campaign_task

    expand_campaign_task.delay(str(campaign_id))


def _new_unsubscribe_link(*, campaign, contact):
    token = secrets.token_urlsafe(32)
    UnsubscribeCapability.objects.create(
        site=campaign.site,
        campaign=campaign,
        contact=contact,
        channel=campaign.channel,
        token_hash=token_hash(token),
    )
    hostname = campaign.site.domains.get(is_canonical=True).hostname
    path = reverse("communications:unsubscribe", kwargs={"token": token})
    return f"https://{hostname}{path}"


def _marketing_body(campaign, unsubscribe_url):
    label = (
        "Unsubscribe" if campaign.channel == Campaign.Channel.EMAIL else "Stop messages"
    )
    return f"{campaign.body.rstrip()}\n\n{label}: {unsubscribe_url}"


@transaction.atomic
def expand_campaign(campaign_id):
    campaign = (
        Campaign.objects.select_for_update()
        .select_related("site", "sms_allowance")
        .get(pk=campaign_id)
    )
    if campaign.status in (Campaign.Status.SENDING, Campaign.Status.SENT):
        return campaign
    if campaign.status != Campaign.Status.SCHEDULED:
        return campaign
    if campaign.scheduled_for and campaign.scheduled_for > timezone.now():
        return campaign
    campaign.status = Campaign.Status.EXPANDING
    campaign.started_at = campaign.started_at or timezone.now()
    campaign.save(update_fields=("status", "started_at", "updated_at"))

    counts = Counter()
    actual_segments = 0
    for contact in audience_contacts(campaign).iterator(
        chunk_size=settings.CAMPAIGN_EXPANSION_BATCH_SIZE
    ):
        recipient, created = CampaignRecipient.objects.get_or_create(
            site=campaign.site,
            campaign=campaign,
            contact=contact,
            defaults={"status": CampaignRecipient.Status.EXCLUDED},
        )
        if not created and hasattr(recipient, "outbound_message"):
            counts[recipient.status] += 1
            actual_segments += recipient.segment_count
            continue
        eligible, reason = contact_eligibility(contact, campaign.channel)
        if not eligible:
            recipient.status = (
                CampaignRecipient.Status.SUPPRESSED
                if "suppressed" in reason.lower()
                else CampaignRecipient.Status.EXCLUDED
            )
            recipient.exclusion_reason = reason
            recipient.save()
            counts[recipient.status] += 1
            continue
        unsubscribe_url = _new_unsubscribe_link(campaign=campaign, contact=contact)
        body = _marketing_body(campaign, unsubscribe_url)
        segments = (
            sms_segment_count(body) if campaign.channel == Campaign.Channel.SMS else 0
        )
        recipient.address = (
            contact.email
            if campaign.channel == Campaign.Channel.EMAIL
            else contact.phone
        )
        recipient.status = CampaignRecipient.Status.QUEUED
        recipient.segment_count = segments
        recipient.exclusion_reason = ""
        recipient.save()
        from .services import enqueue_message

        enqueue_message(
            site=campaign.site,
            kind=OutboundMessage.Kind.CAMPAIGN,
            channel=campaign.channel,
            contact=contact,
            campaign=campaign,
            campaign_recipient=recipient,
            recipient_email=contact.email
            if campaign.channel == Campaign.Channel.EMAIL
            else "",
            recipient_phone=contact.phone
            if campaign.channel == Campaign.Channel.SMS
            else "",
            subject=campaign.subject,
            body=body,
            is_marketing=True,
            unsubscribe_url=unsubscribe_url,
            sms_segments=segments,
            sms_allowance=campaign.sms_allowance,
            dedupe_key=f"campaign:{campaign.id}:{contact.id}",
            dispatch=False,
        )
        actual_segments += segments
        counts[recipient.status] += 1

    if campaign.channel == Campaign.Channel.SMS and (
        actual_segments < campaign.sms_reserved_segments
    ):
        _release_sms_locked(
            campaign=campaign,
            segments=campaign.sms_reserved_segments - actual_segments,
            recipient=None,
        )
    campaign.recipient_count = sum(counts.values())
    campaign.eligible_count = counts[CampaignRecipient.Status.QUEUED]
    campaign.excluded_count = campaign.recipient_count - campaign.eligible_count
    campaign.estimated_segments = actual_segments
    campaign.status = (
        Campaign.Status.SENDING if campaign.eligible_count else Campaign.Status.SENT
    )
    campaign.completed_at = None if campaign.eligible_count else timezone.now()
    campaign.save()
    return campaign


def _release_sms_locked(*, campaign, segments, recipient):
    if not segments or campaign.sms_allowance_id is None:
        return
    allowance = SmsAllowance.objects.select_for_update().get(
        pk=campaign.sms_allowance_id
    )
    released = min(
        segments, allowance.reserved_segments, campaign.sms_reserved_segments
    )
    if not released:
        return
    allowance.reserved_segments -= released
    allowance.save(update_fields=("reserved_segments", "updated_at"))
    campaign.sms_reserved_segments -= released
    campaign.save(update_fields=("sms_reserved_segments", "updated_at"))
    SmsUsageEvent.objects.create(
        site=campaign.site,
        campaign=campaign,
        recipient=recipient,
        allowance=allowance,
        action=SmsUsageEvent.Action.RELEASED,
        segments=released,
    )


@transaction.atomic
def release_sms_for_message(message):
    if not message.sms_segments or not message.campaign_id:
        return
    campaign = Campaign.objects.select_for_update().get(pk=message.campaign_id)
    _release_sms_locked(
        campaign=campaign,
        segments=message.sms_segments,
        recipient=message.campaign_recipient,
    )


@transaction.atomic
def consume_sms_for_message(message):
    if (
        not message.sms_segments
        or not message.campaign_id
        or not message.sms_allowance_id
    ):
        return
    campaign = Campaign.objects.select_for_update().get(pk=message.campaign_id)
    allowance = SmsAllowance.objects.select_for_update().get(
        pk=message.sms_allowance_id
    )
    segments = min(
        message.sms_segments,
        allowance.reserved_segments,
        campaign.sms_reserved_segments,
    )
    allowance.reserved_segments -= segments
    allowance.sent_segments += segments
    allowance.save(update_fields=("reserved_segments", "sent_segments", "updated_at"))
    campaign.sms_reserved_segments -= segments
    campaign.save(update_fields=("sms_reserved_segments", "updated_at"))
    SmsUsageEvent.objects.create(
        site=campaign.site,
        campaign=campaign,
        recipient=message.campaign_recipient,
        allowance=allowance,
        action=SmsUsageEvent.Action.ACCEPTED,
        segments=segments,
    )


@transaction.atomic
def unsubscribe(*, site, token):
    capability = (
        UnsubscribeCapability.objects.select_for_update()
        .select_related("contact")
        .filter(site=site, token_hash=token_hash(token), used_at__isnull=True)
        .first()
    )
    if capability is None:
        return None
    contact = capability.contact
    field = f"{capability.channel}_consent_status"
    if getattr(contact, field) != ConsentStatus.SUPPRESSED:
        setattr(contact, field, ConsentStatus.WITHDRAWN)
        contact.save(update_fields=(field, "updated_at"))
        ConsentRecord.objects.create(
            site=site,
            contact=contact,
            channel=capability.channel,
            status=ConsentStatus.WITHDRAWN,
            source="campaign_unsubscribe",
        )
    capability.used_at = timezone.now()
    capability.save(update_fields=("used_at", "updated_at"))
    queued = OutboundMessage.objects.filter(
        site=site,
        contact=contact,
        channel=capability.channel,
        is_marketing=True,
        status__in=(OutboundMessage.Status.QUEUED, OutboundMessage.Status.FAILED),
    ).select_related("campaign", "campaign_recipient")
    affected_campaign_ids = set()
    for message in queued:
        if message.channel == OutboundMessage.Channel.SMS:
            release_sms_for_message(message)
        message.status = OutboundMessage.Status.UNSUBSCRIBED
        message.unsubscribed_at = timezone.now()
        message.body = ""
        message.unsubscribe_url = ""
        message.save(
            update_fields=(
                "status",
                "unsubscribed_at",
                "body",
                "unsubscribe_url",
                "updated_at",
            )
        )
        if message.campaign_recipient_id:
            CampaignRecipient.objects.filter(pk=message.campaign_recipient_id).update(
                status=CampaignRecipient.Status.UNSUBSCRIBED,
                unsubscribed_at=timezone.now(),
                updated_at=timezone.now(),
            )
        if message.campaign_id:
            affected_campaign_ids.add(message.campaign_id)
    for campaign_id in affected_campaign_ids:
        refresh_campaign_status(campaign_id)
    return capability


def refresh_campaign_status(campaign_id):
    campaign = Campaign.objects.get(pk=campaign_id)
    if campaign.status not in (Campaign.Status.SENDING, Campaign.Status.EXPANDING):
        return campaign
    remaining = campaign.recipients.filter(
        status=CampaignRecipient.Status.QUEUED
    ).exists()
    if not remaining:
        campaign.status = Campaign.Status.SENT
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=("status", "completed_at", "updated_at"))
    return campaign


def campaign_metrics(campaign):
    counts = dict(
        campaign.recipients.values_list("status")
        .annotate(total=Count("id"))
        .values_list("status", "total")
    )
    return {
        "total": campaign.recipients.count(),
        "queued": counts.get(CampaignRecipient.Status.QUEUED, 0),
        "sent": campaign.recipients.filter(sent_at__isnull=False).count(),
        "delivered": campaign.recipients.filter(delivered_at__isnull=False).count(),
        "opened": campaign.recipients.filter(opened_at__isnull=False).count(),
        "clicked": campaign.recipients.filter(clicked_at__isnull=False).count(),
        "bounced": counts.get(CampaignRecipient.Status.BOUNCED, 0),
        "failed": counts.get(CampaignRecipient.Status.FAILED, 0),
        "unsubscribed": counts.get(CampaignRecipient.Status.UNSUBSCRIBED, 0),
        "excluded": counts.get(CampaignRecipient.Status.EXCLUDED, 0)
        + counts.get(CampaignRecipient.Status.SUPPRESSED, 0),
    }


@transaction.atomic
def duplicate_campaign(*, campaign, actor):
    return Campaign.objects.create(
        site=campaign.site,
        name=f"Copy of {campaign.name}"[:160],
        channel=campaign.channel,
        subject=campaign.subject,
        body=campaign.body,
        audience=campaign.audience,
        audience_tag=campaign.audience_tag,
        audience_occurrence=campaign.audience_occurrence,
        response_filter=campaign.response_filter,
        source_blog_post=campaign.source_blog_post,
        duplicated_from=campaign,
        created_by=actor,
    )


@transaction.atomic
def queue_campaign_test(*, campaign, email="", phone="", confirm_sms_usage=False):
    if not channel_is_configured(campaign.channel):
        raise CampaignUnavailable(
            f"{campaign.get_channel_display()} delivery is not configured."
        )
    segments = 0
    allowance = None
    if campaign.channel == Campaign.Channel.SMS:
        if not confirm_sms_usage:
            raise CampaignUnavailable("Confirm SMS usage before sending a test.")
        segments = sms_segment_count(f"TEST: {campaign.body}")
        allowance = SmsAllowance.objects.select_for_update().get(
            pk=current_sms_allowance(campaign.site).pk
        )
        if allowance.remaining_segments < segments:
            raise SmsLimitExceeded("No SMS segments are available for this test.")
        allowance.reserved_segments += segments
        allowance.save(update_fields=("reserved_segments", "updated_at"))
        campaign.sms_allowance = allowance
        campaign.sms_reserved_segments += segments
        campaign.save(
            update_fields=("sms_allowance", "sms_reserved_segments", "updated_at")
        )
        SmsUsageEvent.objects.create(
            site=campaign.site,
            campaign=campaign,
            allowance=allowance,
            action=SmsUsageEvent.Action.RESERVED,
            segments=segments,
        )
    from .services import enqueue_message

    return enqueue_message(
        site=campaign.site,
        campaign=campaign,
        kind=OutboundMessage.Kind.CAMPAIGN_TEST,
        channel=campaign.channel,
        recipient_email=email,
        recipient_phone=phone,
        subject=f"TEST: {campaign.subject}" if campaign.subject else "TEST message",
        body=f"TEST MESSAGE\n\n{campaign.body}",
        sms_segments=segments,
        sms_allowance=allowance,
    )
