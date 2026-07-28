import hashlib
import secrets

from django.db import transaction
from django.utils import timezone

from contacts.models import Contact

from .models import (
    Event,
    EventOccurrence,
    Invitation,
    Participant,
    Registration,
    RegistrationHistory,
)


class CapacityExceeded(Exception):
    pass


class RegistrationUnavailable(Exception):
    pass


def invitation_token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@transaction.atomic
def create_invitations(*, site, occurrence, contacts, actor):
    occurrence = EventOccurrence.objects.select_for_update().get(
        pk=occurrence.pk, site=site
    )
    invitations = []
    for contact in contacts:
        if contact.site_id != site.id or not contact.email:
            continue
        token = secrets.token_urlsafe(32)
        invitation, _ = Invitation.objects.update_or_create(
            site=site,
            occurrence=occurrence,
            contact=contact,
            defaults={
                "token_hash": invitation_token_hash(token),
                "status": Invitation.Status.PENDING,
                "sent_at": timezone.now(),
                "expires_at": occurrence.ends_at,
                "created_by": actor,
            },
        )
        invitations.append((invitation, token))
    return invitations


def invitation_for_token(*, site, token):
    return (
        Invitation.objects.for_site(site)
        .select_related("contact", "occurrence__event")
        .filter(
            token_hash=invitation_token_hash(token),
            status__in=(Invitation.Status.PENDING, Invitation.Status.RESPONDED),
            expires_at__gte=timezone.now(),
        )
        .first()
    )


def _validate_registration_access(occurrence, source, invitation):
    if occurrence.status != EventOccurrence.Status.SCHEDULED:
        raise RegistrationUnavailable(
            "This event occurrence is not accepting responses."
        )
    if occurrence.event.status != Event.Status.PUBLISHED:
        raise RegistrationUnavailable("This event is not accepting responses.")
    if occurrence.event.visibility == Event.Visibility.INVITE_ONLY and source not in (
        Registration.Source.INVITATION,
        Registration.Source.MANAGER,
    ):
        raise RegistrationUnavailable("A valid invitation is required for this event.")
    if source == Registration.Source.INVITATION:
        if invitation is None or invitation.occurrence_id != occurrence.id:
            raise RegistrationUnavailable(
                "That invitation is not valid for this event."
            )


@transaction.atomic
def save_response(
    *,
    occurrence,
    contact,
    response,
    guests,
    source,
    invitation=None,
    actor=None,
):
    occurrence = (
        EventOccurrence.objects.select_for_update()
        .select_related("event")
        .get(pk=occurrence.pk)
    )
    _validate_registration_access(occurrence, source, invitation)
    if contact.site_id != occurrence.site_id:
        raise RegistrationUnavailable("The contact does not belong to this site.")
    if response != Registration.Response.GOING:
        guests = []
    if response == Registration.Response.GOING and (
        not contact.first_name.strip() or not contact.last_name.strip()
    ):
        raise RegistrationUnavailable(
            "A first and last name are required for the primary participant."
        )
    if any(
        not guest.get("first_name", "").strip()
        or not guest.get("last_name", "").strip()
        for guest in guests
    ):
        raise RegistrationUnavailable(
            "A first and last name are required for every guest."
        )
    if len(guests) > occurrence.event.max_guests:
        raise RegistrationUnavailable("The guest limit for this event was exceeded.")

    registration = (
        Registration.objects.select_for_update()
        .filter(occurrence=occurrence, contact=contact)
        .first()
    )
    paid_event = occurrence.ticket_types.filter(is_active=True).exists()
    if (
        registration is not None
        and registration.payment_status == Registration.PaymentStatus.PAID
        and response != registration.response
    ):
        raise RegistrationUnavailable(
            "A paid registration must be refunded before its response can change."
        )
    active_others = Participant.objects.filter(
        site=occurrence.site,
        registration__occurrence=occurrence,
        registration__response=Registration.Response.GOING,
        registration__payment_status__in=(
            Registration.PaymentStatus.NOT_REQUIRED,
            Registration.PaymentStatus.PAID,
        ),
        status=Participant.Status.ACTIVE,
    )
    if registration is not None:
        active_others = active_others.exclude(registration=registration)
    requested_spots = (
        1 + len(guests)
        if response == Registration.Response.GOING and not paid_event
        else 0
    )
    if (
        occurrence.capacity is not None
        and active_others.count() + requested_spots > occurrence.capacity
    ):
        raise CapacityExceeded(
            "There are not enough remaining spots for this response and its guests."
        )

    previous_response = registration.response if registration else ""
    if registration is None:
        registration = Registration.objects.create(
            site=occurrence.site,
            occurrence=occurrence,
            contact=contact,
            invitation=invitation,
            response=response,
            source=source,
            payment_status=(
                Registration.PaymentStatus.PENDING
                if paid_event and response == Registration.Response.GOING
                else Registration.PaymentStatus.NOT_REQUIRED
            ),
        )
    else:
        registration.response = response
        registration.source = source
        registration.payment_status = (
            Registration.PaymentStatus.PENDING
            if paid_event and response == Registration.Response.GOING
            else Registration.PaymentStatus.NOT_REQUIRED
        )
        if invitation is not None:
            registration.invitation = invitation
        registration.save(
            update_fields=(
                "response",
                "source",
                "payment_status",
                "invitation",
                "responded_at",
                "updated_at",
            )
        )

    registration.participants.filter(status=Participant.Status.ACTIVE).update(
        status=Participant.Status.CANCELED
    )
    participants = []
    if response == Registration.Response.GOING:
        participants.append(
            Participant.objects.create(
                site=occurrence.site,
                registration=registration,
                first_name=contact.first_name,
                last_name=contact.last_name,
                email=contact.email,
                phone=contact.phone,
                is_primary=True,
            )
        )
        participants.extend(
            Participant.objects.create(
                site=occurrence.site,
                registration=registration,
                first_name=guest["first_name"],
                last_name=guest["last_name"],
                email=guest.get("email", ""),
                phone=guest.get("phone", ""),
            )
            for guest in guests
        )

    history = RegistrationHistory.objects.create(
        site=occurrence.site,
        registration=registration,
        previous_response=previous_response,
        new_response=response,
        guest_count=len(guests) if response == Registration.Response.GOING else 0,
        participant_names=[participant.display_name for participant in participants],
        source=source,
        changed_by=actor,
    )
    if invitation is not None:
        invitation.status = Invitation.Status.RESPONDED
        invitation.save(update_fields=("status", "updated_at"))
    return registration, history


@transaction.atomic
def save_public_response(
    *, site, occurrence, response, first_name, last_name, email, guests
):
    normalized_email = email.strip().casefold()
    contact = (
        Contact.objects.select_for_update()
        .filter(site=site, normalized_email=normalized_email)
        .first()
    )
    if contact is None:
        contact = Contact.objects.create(
            site=site,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=normalized_email,
        )
    else:
        contact.first_name = first_name.strip()
        contact.last_name = last_name.strip()
        if contact.archived_at is not None:
            contact.archived_at = None
        contact.save(
            update_fields=("first_name", "last_name", "archived_at", "updated_at")
        )
    return save_response(
        occurrence=occurrence,
        contact=contact,
        response=response,
        guests=guests,
        source=Registration.Source.PUBLIC,
    )
