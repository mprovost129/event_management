from django.utils import timezone

from communications.models import OutboundMessage
from contacts.models import Contact
from events.models import Event, EventOccurrence, Invitation, Registration
from ops.models import AuditEvent
from payments.models import ConnectedAccount, TicketType
from subscriptions.models import PlatformSubscription

from .models import SiteRole


def pilot_readiness(site, *, now=None):
    """Return the current, read-only pilot readiness state for one site."""

    now = now or timezone.now()
    occurrence = (
        EventOccurrence.objects.for_site(site)
        .filter(
            event__status=Event.Status.PUBLISHED,
            status=EventOccurrence.Status.SCHEDULED,
            ends_at__gt=now,
        )
        .select_related("event")
        .order_by("starts_at")
        .first()
    )
    connected = ConnectedAccount.objects.filter(site=site).first()
    subscription = site.platform_subscription
    ticketed = bool(
        occurrence
        and TicketType.objects.for_site(site)
        .filter(occurrence=occurrence, is_active=True)
        .exists()
    )
    invite_only = bool(
        occurrence and occurrence.event.visibility == Event.Visibility.INVITE_ONLY
    )
    invitation_sent = bool(
        occurrence
        and Invitation.objects.for_site(site)
        .filter(occurrence=occurrence, sent_at__isnull=False)
        .exists()
    )
    registration_recorded = bool(
        occurrence
        and Registration.objects.for_site(site).filter(occurrence=occurrence).exists()
    )
    delivery_tested = bool(
        occurrence
        and OutboundMessage.objects.for_site(site)
        .filter(
            occurrence=occurrence,
            status__in=(
                OutboundMessage.Status.SENT,
                OutboundMessage.Status.DELIVERED,
                OutboundMessage.Status.OPENED,
                OutboundMessage.Status.CLICKED,
            ),
        )
        .exists()
    )

    required = [
        {
            "key": "subscriber_admin",
            "label": "Subscriber owner assigned",
            "description": "An active subscriber admin owns the site and its billing.",
            "complete": SiteRole.objects.filter(
                site=site,
                role=SiteRole.Role.SUBSCRIBER_ADMIN,
                is_active=True,
            ).exists(),
        },
        {
            "key": "active_access",
            "label": "Site access active",
            "description": "The trial or subscription currently permits public traffic.",
            "complete": site.accepts_public_traffic,
        },
        {
            "key": "site_published",
            "label": "Website published",
            "description": "Your group's site is visible from its Gather HQs address.",
            "complete": site.is_published,
        },
        {
            "key": "contacts_entered",
            "label": "Contact list started",
            "description": "At least one real contact is available for invitations.",
            "complete": Contact.objects.for_site(site).exists(),
        },
        {
            "key": "upcoming_event",
            "label": "Upcoming event published",
            "description": "A scheduled occurrence is available for the pilot group.",
            "complete": occurrence is not None,
        },
        {
            "key": "commerce_ready",
            "label": (
                "Ticket payments ready"
                if ticketed
                else "No payment setup needed"
                if occurrence
                else "Payment setup follows the event"
            ),
            "description": (
                "Stripe can accept charges and send payouts for this paid event."
                if ticketed
                else "The next event is free, so Stripe Connect is not a launch blocker."
                if occurrence
                else "Create the event first; only paid events require Stripe Connect."
            ),
            "complete": not ticketed or bool(connected and connected.commerce_ready),
            "conditional": True,
        },
        {
            "key": "refund_policy",
            "label": (
                "Refund policy published" if ticketed else "No refund policy needed yet"
            ),
            "description": (
                "Buyers are told the refund terms before they pay."
                if ticketed
                else "Set one before you start selling tickets."
            ),
            "complete": not ticketed or bool(site.default_refund_policy.strip()),
            "conditional": True,
        },
        {
            "key": "invitation_path",
            "label": "First invitation sent"
            if invite_only
            else "Signup path available",
            "description": (
                "Invite-only events need at least one sent invitation before launch."
                if invite_only
                else "The next event accepts registrations from its shareable event page."
            ),
            "complete": not occurrence or not invite_only or invitation_sent,
            "conditional": True,
        },
    ]

    recommended = [
        {
            "key": "billing_selected",
            "label": "Billing schedule selected",
            "description": "Choose monthly or yearly billing before the trial ends.",
            "complete": bool(
                subscription.stripe_customer_id
                and subscription.stripe_subscription_id
                and subscription.billing_interval
                and subscription.status
                in (
                    PlatformSubscription.Status.TRIALING,
                    PlatformSubscription.Status.ACTIVE,
                )
            ),
        },
        {
            "key": "venue_complete",
            "label": "Venue details confirmed",
            "description": "Give attendees a venue name and street address.",
            "complete": bool(
                occurrence
                and occurrence.venue_name.strip()
                and occurrence.venue_address.strip()
            ),
        },
        {
            "key": "response_recorded",
            "label": "Registration flow rehearsed",
            "description": "Record one real or reversible test response before inviting everyone.",
            "complete": registration_recorded,
        },
        {
            "key": "delivery_tested",
            "label": "Event email delivered",
            "description": "Confirm that at least one event message reaches a real inbox.",
            "complete": delivery_tested,
        },
        {
            "key": "backup_manager",
            "label": "Backup manager added",
            "description": "A second trusted person can operate the roster if needed.",
            "complete": SiteRole.objects.filter(
                site=site,
                role=SiteRole.Role.SITE_MANAGER,
                is_active=True,
            ).exists(),
        },
        {
            "key": "mailing_address",
            "label": "Mailing address on file",
            "description": (
                "Required by law at the bottom of every newsletter. "
                "Newsletters cannot be sent until this is set."
            ),
            "complete": bool(site.postal_address.strip()),
        },
        {
            "key": "data_exported",
            "label": "Data export rehearsed",
            "description": "Download one site export and store it securely before event day.",
            "complete": AuditEvent.objects.filter(
                site_id=site.id, action="site.data_exported"
            ).exists(),
        },
    ]

    required_complete = sum(check["complete"] for check in required)
    recommended_complete = sum(check["complete"] for check in recommended)
    return {
        "ok": required_complete == len(required),
        "required": required,
        "recommended": recommended,
        "required_complete": required_complete,
        "required_total": len(required),
        "required_remaining": len(required) - required_complete,
        "required_percent": round(required_complete * 100 / len(required)),
        "recommended_complete": recommended_complete,
        "recommended_total": len(recommended),
        "recommended_remaining": len(recommended) - recommended_complete,
        "occurrence": occurrence,
        "ticketed": ticketed,
        "invite_only": invite_only,
        "next": next((check for check in required if not check["complete"]), None),
    }
