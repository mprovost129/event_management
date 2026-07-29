from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from attendance.models import AttendanceStatus
from communications.models import Campaign, CampaignRecipient
from contacts.models import MemberSubscription
from events.models import EventOccurrence, Invitation, Participant, Registration
from payments.models import Order
from payments.services import commerce_summary
from reviews.models import Review


def _active_participants(site):
    return Participant.objects.for_site(site).filter(
        status=Participant.Status.ACTIVE,
        registration__response=Registration.Response.GOING,
        registration__payment_status__in=(
            Registration.PaymentStatus.NOT_REQUIRED,
            Registration.PaymentStatus.PAID,
        ),
    )


def site_summary(site, *, now=None):
    now = now or timezone.now()
    invitations = Invitation.objects.for_site(site)
    registrations = Registration.objects.for_site(site)
    participants = _active_participants(site)
    ended_participants = participants.filter(registration__occurrence__ends_at__lte=now)
    checked_in = AttendanceStatus.objects.for_site(site).filter(
        participant__in=participants, checked_in_at__isnull=False
    )
    ended_checked_in = checked_in.filter(
        participant__registration__occurrence__ends_at__lte=now
    )
    visible_reviews = (
        Review.objects.for_site(site)
        .filter(deleted_at__isnull=True)
        .exclude(moderation_status=Review.ModerationStatus.HIDDEN)
    )
    rating = visible_reviews.aggregate(average=Avg("rating"))
    capacity = (
        EventOccurrence.objects.for_site(site)
        .filter(capacity__isnull=False)
        .aggregate(total=Sum("capacity"))["total"]
        or 0
    )
    invited_count = invitations.count()
    responded_invites = invitations.filter(status=Invitation.Status.RESPONDED).count()
    ended_count = ended_participants.count()
    checked_in_ended_count = ended_checked_in.count()
    finance = commerce_summary(site)
    memberships = MemberSubscription.objects.for_site(site)
    sent_campaigns = Campaign.objects.for_site(site).filter(status=Campaign.Status.SENT)
    campaign_recipients = CampaignRecipient.objects.for_site(site)
    return {
        "invitations": invited_count,
        "registrations": registrations.count(),
        "going": registrations.filter(response=Registration.Response.GOING).count(),
        "maybe": registrations.filter(response=Registration.Response.MAYBE).count(),
        "not_going": registrations.filter(
            response=Registration.Response.NOT_GOING
        ).count(),
        "invite_response_rate": (
            round(responded_invites * 100 / invited_count, 1) if invited_count else 0
        ),
        "participants": participants.count(),
        "guests": participants.filter(is_primary=False).count(),
        "capacity": capacity,
        "checked_in": checked_in.count(),
        "attendance_rate": (
            round(checked_in_ended_count * 100 / ended_count, 1) if ended_count else 0
        ),
        "no_show_rate": (
            round((ended_count - checked_in_ended_count) * 100 / ended_count, 1)
            if ended_count
            else 0
        ),
        "review_count": visible_reviews.count(),
        "rating_average": rating["average"],
        "campaigns_sent": sent_campaigns.count(),
        "campaign_failures": campaign_recipients.filter(
            status__in=(
                CampaignRecipient.Status.FAILED,
                CampaignRecipient.Status.BOUNCED,
            )
        ).count(),
        "active_members": memberships.filter(
            status=MemberSubscription.Status.ACTIVE
        ).count(),
        "past_due_members": memberships.filter(
            status=MemberSubscription.Status.PAST_DUE
        ).count(),
        "canceled_members": memberships.filter(
            status=MemberSubscription.Status.CANCELED
        ).count(),
        "expired_members": memberships.filter(
            status=MemberSubscription.Status.EXPIRED
        ).count(),
        "ticket_gross_display": Decimal(finance["ticket_gross_cents"]) / 100,
        "ticket_net_display": Decimal(finance["ticket_net_cents"]) / 100,
        "refunds_display": Decimal(finance["refunds_cents"]) / 100,
        "member_dues_display": Decimal(finance["member_dues_cents"]) / 100,
        "platform_fee_net_display": Decimal(finance["platform_fee_net_cents"]) / 100,
        **finance,
    }


def occurrence_comparison(site, *, now=None):
    now = now or timezone.now()
    occurrences = list(
        EventOccurrence.objects.for_site(site)
        .select_related("event")
        .order_by("-starts_at")
    )
    occurrence_ids = [occurrence.id for occurrence in occurrences]
    if not occurrence_ids:
        return []

    registration_stats = {
        row["occurrence_id"]: row
        for row in Registration.objects.for_site(site)
        .filter(occurrence_id__in=occurrence_ids)
        .values("occurrence_id")
        .annotate(
            registrations=Count("id"),
            going=Count("id", filter=Q(response=Registration.Response.GOING)),
            maybe=Count("id", filter=Q(response=Registration.Response.MAYBE)),
            not_going=Count("id", filter=Q(response=Registration.Response.NOT_GOING)),
            payment_pending=Count(
                "id", filter=Q(payment_status=Registration.PaymentStatus.PENDING)
            ),
        )
    }
    participant_stats = {
        row["registration__occurrence_id"]: row
        for row in _active_participants(site)
        .filter(registration__occurrence_id__in=occurrence_ids)
        .values("registration__occurrence_id")
        .annotate(
            participants=Count("id"),
            guests=Count("id", filter=Q(is_primary=False)),
        )
    }
    attendance_stats = {
        row["participant__registration__occurrence_id"]: row["checked_in"]
        for row in AttendanceStatus.objects.for_site(site)
        .filter(
            participant__registration__occurrence_id__in=occurrence_ids,
            participant__registration__response=Registration.Response.GOING,
            participant__registration__payment_status__in=(
                Registration.PaymentStatus.NOT_REQUIRED,
                Registration.PaymentStatus.PAID,
            ),
            participant__status=Participant.Status.ACTIVE,
            checked_in_at__isnull=False,
        )
        .values("participant__registration__occurrence_id")
        .annotate(checked_in=Count("id"))
    }
    invitation_stats = {
        row["occurrence_id"]: row
        for row in Invitation.objects.for_site(site)
        .filter(occurrence_id__in=occurrence_ids)
        .values("occurrence_id")
        .annotate(
            invited=Count("id"),
            responded=Count("id", filter=Q(status=Invitation.Status.RESPONDED)),
        )
    }
    financial_stats = {
        row["occurrence_id"]: row
        for row in Order.objects.for_site(site)
        .filter(
            occurrence_id__in=occurrence_ids,
            status__in=(
                Order.Status.PAID,
                Order.Status.PARTIALLY_REFUNDED,
                Order.Status.REFUNDED,
                Order.Status.DISPUTED,
            ),
        )
        .values("occurrence_id")
        .annotate(
            gross=Sum("total_cents"),
            refunds=Sum("refunded_cents"),
            fees=Sum("stripe_fee_cents"),
            application_fees=Sum("application_fee_cents"),
            application_fee_refunds=Sum("application_fee_refunded_cents"),
        )
    }
    review_stats = {
        row["occurrence_id"]: row
        for row in Review.objects.for_site(site)
        .filter(occurrence_id__in=occurrence_ids, deleted_at__isnull=True)
        .exclude(moderation_status=Review.ModerationStatus.HIDDEN)
        .values("occurrence_id")
        .annotate(review_count=Count("id"), rating_average=Avg("rating"))
    }

    results = []
    for occurrence in occurrences:
        registrations = registration_stats.get(occurrence.id, {})
        participants = participant_stats.get(occurrence.id, {})
        invitations = invitation_stats.get(occurrence.id, {})
        finance = financial_stats.get(occurrence.id, {})
        reviews = review_stats.get(occurrence.id, {})
        participant_count = participants.get("participants", 0)
        checked_in = attendance_stats.get(occurrence.id, 0)
        invited = invitations.get("invited", 0)
        gross = finance.get("gross") or 0
        refunds = finance.get("refunds") or 0
        fees = finance.get("fees") or 0
        application_fees = finance.get("application_fees") or 0
        application_fee_refunds = finance.get("application_fee_refunds") or 0
        results.append(
            {
                "occurrence": occurrence,
                "registrations": registrations.get("registrations", 0),
                "going": registrations.get("going", 0),
                "maybe": registrations.get("maybe", 0),
                "not_going": registrations.get("not_going", 0),
                "payment_pending": registrations.get("payment_pending", 0),
                "participants": participant_count,
                "guests": participants.get("guests", 0),
                "checked_in": checked_in,
                "attendance_rate": (
                    round(checked_in * 100 / participant_count, 1)
                    if participant_count
                    else 0
                ),
                "invited": invited,
                "invite_response_rate": (
                    round(invitations.get("responded", 0) * 100 / invited, 1)
                    if invited
                    else 0
                ),
                "gross_cents": gross,
                "refunds_cents": refunds,
                "gross_display": Decimal(gross) / 100,
                "refunds_display": Decimal(refunds) / 100,
                "net_display": Decimal(
                    gross - refunds - fees - application_fees + application_fee_refunds
                )
                / 100,
                "review_count": reviews.get("review_count", 0),
                "rating_average": reviews.get("rating_average"),
                "is_complete": occurrence.ends_at <= now,
                "is_canceled": occurrence.status == EventOccurrence.Status.CANCELED,
            }
        )
    return results


def event_comparison(site, *, occurrence_rows=None):
    if occurrence_rows is None:
        occurrence_rows = occurrence_comparison(site)
    series = {}
    for row in occurrence_rows:
        event = row["occurrence"].event
        totals = series.setdefault(
            event.id,
            {
                "event": event,
                "occurrences": 0,
                "registrations": 0,
                "participants": 0,
                "checked_in": 0,
                "gross_cents": 0,
                "refunds_cents": 0,
                "review_count": 0,
                "rating_points": Decimal(0),
            },
        )
        totals["occurrences"] += 1
        for key in (
            "registrations",
            "participants",
            "checked_in",
            "gross_cents",
            "refunds_cents",
            "review_count",
        ):
            totals[key] += row[key]
        if row["rating_average"] is not None:
            totals["rating_points"] += (
                Decimal(str(row["rating_average"])) * row["review_count"]
            )

    results = []
    for totals in series.values():
        review_count = totals["review_count"]
        totals["rating_average"] = (
            totals.pop("rating_points") / review_count if review_count else None
        )
        totals["gross_display"] = Decimal(totals["gross_cents"]) / 100
        totals["refunds_display"] = Decimal(totals["refunds_cents"]) / 100
        results.append(totals)
    return sorted(results, key=lambda row: row["event"].title.casefold())
