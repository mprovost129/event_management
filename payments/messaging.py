from communications.models import OutboundMessage
from communications.services import enqueue_message


def queue_ticket_receipt(order):
    if not order.purchaser.email:
        return None
    tickets = order.lines.first().tickets.select_related("participant")
    ticket_lines = "\n".join(
        f"- {ticket.participant.display_name}: {ticket.display_code}"
        for ticket in tickets
    )
    return enqueue_message(
        site=order.site,
        kind=OutboundMessage.Kind.TICKET_RECEIPT,
        recipient_email=order.purchaser.email,
        subject=f"Tickets: {order.occurrence.event.title}",
        body=(
            f"Your payment for {order.occurrence.event.title} is confirmed.\n\n"
            f"Tickets:\n{ticket_lines}\n\n"
            f"Total: {order.total_cents / 100:.2f} {order.currency.upper()}"
        ),
        dedupe_key=f"ticket-receipt:{order.id}",
        occurrence=order.occurrence,
        registration=order.registration,
    )


def queue_membership_receipt(member_subscription):
    contact = member_subscription.member.contact
    if not contact.email:
        return None
    return enqueue_message(
        site=member_subscription.site,
        kind=OutboundMessage.Kind.MEMBERSHIP_RECEIPT,
        recipient_email=contact.email,
        subject=f"Membership confirmed: {member_subscription.plan.name}",
        body=(
            f"Your {member_subscription.plan.name} membership is active.\n\n"
            "Membership does not automatically RSVP you to events. Please respond "
            "separately for each event you plan to attend."
        ),
        dedupe_key=f"membership-receipt:{member_subscription.id}",
    )
