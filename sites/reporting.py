from decimal import Decimal

from django.db.models import Avg, Sum
from django.utils import timezone

from attendance.models import AttendanceStatus
from communications.models import Campaign, CampaignRecipient
from contacts.models import MemberSubscription
from events.models import Event, EventOccurrence, Invitation, Participant, Registration
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
        **finance,
    }


def event_comparison(site):
    results = []
    for event in Event.objects.for_site(site).prefetch_related("occurrences"):
        occurrences = event.occurrences.all()
        registrations = Registration.objects.filter(occurrence__in=occurrences)
        participants = _active_participants(site).filter(
            registration__occurrence__in=occurrences
        )
        checked_in = AttendanceStatus.objects.for_site(site).filter(
            participant__in=participants, checked_in_at__isnull=False
        )
        orders = Order.objects.for_site(site).filter(
            occurrence__in=occurrences,
            status__in=(
                Order.Status.PAID,
                Order.Status.PARTIALLY_REFUNDED,
                Order.Status.REFUNDED,
                Order.Status.DISPUTED,
            ),
        )
        reviews = (
            Review.objects.for_site(site)
            .filter(occurrence__in=occurrences, deleted_at__isnull=True)
            .exclude(moderation_status=Review.ModerationStatus.HIDDEN)
        )
        money = orders.aggregate(
            gross=Sum("total_cents"), refunds=Sum("refunded_cents")
        )
        rating = reviews.aggregate(average=Avg("rating"))
        results.append(
            {
                "event": event,
                "occurrences": occurrences.count(),
                "registrations": registrations.count(),
                "participants": participants.count(),
                "checked_in": checked_in.count(),
                "gross_cents": money["gross"] or 0,
                "refunds_cents": money["refunds"] or 0,
                "gross_display": Decimal(money["gross"] or 0) / 100,
                "refunds_display": Decimal(money["refunds"] or 0) / 100,
                "review_count": reviews.count(),
                "rating_average": rating["average"],
            }
        )
    return results
