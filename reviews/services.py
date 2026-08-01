from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from attendance.models import AttendanceStatus
from communications.models import OutboundMessage
from communications.services import enqueue_message
from events.models import Participant
from ops.services import record_audit_event

from .models import Review, ReviewModeration, ReviewReport

REVIEW_TOKEN_SALT = "gather-hqs.review-capability.v1"


def review_token(participant):
    return signing.dumps(
        {"participant_id": str(participant.id), "site_id": str(participant.site_id)},
        salt=REVIEW_TOKEN_SALT,
        compress=True,
    )


def participant_for_token(*, site, token):
    try:
        payload = signing.loads(
            token,
            salt=REVIEW_TOKEN_SALT,
            max_age=settings.REVIEW_TOKEN_MAX_AGE_DAYS * 86400,
        )
    except signing.BadSignature:
        return None
    if payload.get("site_id") != str(site.id):
        return None
    return (
        Participant.objects.for_site(site)
        .select_related("registration__occurrence", "attendance_status")
        .filter(pk=payload.get("participant_id"))
        .first()
    )


def participant_can_review(participant, *, now=None):
    now = now or timezone.now()
    try:
        checked_in = participant.attendance_status.checked_in_at is not None
    except AttendanceStatus.DoesNotExist:
        checked_in = False
    return (
        checked_in
        and participant.status == Participant.Status.ACTIVE
        and participant.registration.occurrence.ends_at <= now
    )


@transaction.atomic
def save_review(*, participant, rating, comment):
    participant = (
        Participant.objects.select_for_update(of=("self",))
        .select_related("registration__occurrence", "attendance_status")
        .get(pk=participant.pk)
    )
    if not participant_can_review(participant):
        raise ValidationError("Only checked-in attendees can review after the event.")
    review, created = Review.objects.select_for_update().get_or_create(
        site=participant.site,
        participant=participant,
        defaults={
            "occurrence": participant.registration.occurrence,
            "display_name": participant.display_name,
            "rating": rating,
            "comment": comment,
        },
    )
    if not created:
        review.rating = rating
        review.comment = comment
        review.deleted_at = None
        review.edited_at = timezone.now()
        review.save(
            update_fields=(
                "rating",
                "comment",
                "deleted_at",
                "edited_at",
                "updated_at",
            )
        )
    return review, created


@transaction.atomic
def delete_review(*, review):
    review = Review.objects.select_for_update().get(pk=review.pk)
    review.comment = ""
    review.deleted_at = timezone.now()
    review.edited_at = timezone.now()
    review.save(update_fields=("comment", "deleted_at", "edited_at", "updated_at"))
    return review


@transaction.atomic
def respond_to_review(*, review, actor, response):
    review = Review.objects.select_for_update().get(pk=review.pk)
    review.response = response.strip()
    review.responded_by = actor
    review.responded_at = timezone.now()
    review.save(
        update_fields=("response", "responded_by", "responded_at", "updated_at")
    )
    return review


@transaction.atomic
def report_review(*, review, actor, reason, request=None):
    report = ReviewReport.objects.create(
        site=review.site, review=review, reported_by=actor, reason=reason.strip()
    )
    if review.moderation_status == Review.ModerationStatus.VISIBLE:
        review.moderation_status = Review.ModerationStatus.REPORTED
        review.save(update_fields=("moderation_status", "updated_at"))
    record_audit_event(
        action="review.reported",
        actor=actor,
        site_id=review.site_id,
        target=review,
        summary={"report_id": str(report.id)},
        request=request,
    )
    return report


@transaction.atomic
def moderate_review(*, review, actor, action, reason, request=None):
    if action not in ReviewModeration.Action.values:
        raise ValidationError("Unknown moderation action.")
    review = Review.objects.select_for_update().get(pk=review.pk)
    review.moderation_status = (
        Review.ModerationStatus.HIDDEN
        if action == ReviewModeration.Action.HIDDEN
        else Review.ModerationStatus.VISIBLE
    )
    review.save(update_fields=("moderation_status", "updated_at"))
    moderation = ReviewModeration.objects.create(
        site=review.site,
        review=review,
        actor=actor,
        action=action,
        reason=reason.strip(),
    )
    if action == ReviewModeration.Action.RESTORED:
        review.reports.filter(resolved_at__isnull=True).update(
            resolved_at=timezone.now()
        )
    record_audit_event(
        action=f"review.moderated.{action}",
        actor=actor,
        site_id=review.site_id,
        target=review,
        summary={"reason": reason[:200]},
        request=request,
    )
    return moderation


def queue_due_review_requests(*, limit=500, now=None):
    now = now or timezone.now()
    statuses = (
        AttendanceStatus.objects.filter(
            checked_in_at__isnull=False,
            participant__registration__occurrence__ends_at__lte=now,
            participant__email__gt="",
            participant__review__isnull=True,
        )
        .select_related("site", "participant__registration__occurrence__event")
        .order_by("participant__registration__occurrence__ends_at")[:limit]
    )
    queued = 0
    for status in statuses:
        participant = status.participant
        token = review_token(participant)
        hostname = status.site.domains.get(is_canonical=True).hostname
        path = reverse("reviews:submit", kwargs={"token": token})
        dedupe_key = f"review-request:{participant.id}"
        already_queued = OutboundMessage.objects.filter(
            site=status.site, dedupe_key=dedupe_key
        ).exists()
        enqueue_message(
            site=status.site,
            kind=OutboundMessage.Kind.REVIEW_REQUEST,
            recipient_email=participant.email,
            subject=f"How was {participant.registration.occurrence.event.title}?",
            body=f"Thanks for attending. Share your review:\n\nhttps://{hostname}{path}",
            dedupe_key=dedupe_key,
            contact=participant.registration.contact,
        )
        if not already_queued:
            queued += 1
    return queued
