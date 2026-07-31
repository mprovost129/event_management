from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
from django.db import connections
from django.urls import reverse
from django.utils import timezone

from communications.models import OutboundMessage
from contacts.models import Contact
from events.messaging import queue_confirmation
from events.models import Event, Invitation, Participant, Registration
from events.registration import (
    CapacityExceeded,
    RegistrationUnavailable,
    create_invitations,
    invitation_for_token,
    public_rsvp_manage_token,
    save_public_response,
    save_response,
)
from events.services import create_event_series
from sites.services import create_subscriber_site
from users.models import User


def phase_three_fixture(
    *, capacity=20, max_guests=3, visibility=Event.Visibility.PUBLIC
):
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
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    starts_at = timezone.now().astimezone(ZoneInfo(site.timezone)) + timedelta(days=7)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Friday dance",
            "slug": "friday-dance",
            "description": "An evening of country line dancing.",
            "host_name": "Pat",
            "visibility": visibility,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": max_guests,
        },
        first_start=starts_at,
        first_end=starts_at + timedelta(hours=2),
        venue_name="Town Hall",
        capacity=capacity,
    )
    return owner, site, event, event.occurrences.get()


@pytest.mark.django_db
def test_invitation_token_is_hashed_and_supports_invite_only_response():
    owner, site, _, occurrence = phase_three_fixture(
        visibility=Event.Visibility.INVITE_ONLY
    )
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )

    invitation, token = create_invitations(
        site=site, occurrence=occurrence, contacts=[contact], actor=owner
    )[0]
    resolved = invitation_for_token(site=site, token=token)
    registration, history = save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        guests=[{"first_name": "Sam", "last_name": "Guest"}],
        source=Registration.Source.INVITATION,
        invitation=invitation,
    )

    invitation.refresh_from_db()
    assert token != invitation.token_hash
    assert token not in invitation.token_hash
    assert resolved == invitation
    assert invitation.status == Invitation.Status.RESPONDED
    assert history.guest_count == 1
    assert list(
        registration.participants.filter(status=Participant.Status.ACTIVE).values_list(
            "first_name", "last_name"
        )
    ) == [("Alex", "Dancer"), ("Sam", "Guest")]


@pytest.mark.django_db
def test_invite_only_event_rejects_public_response_without_invitation():
    _, site, _, occurrence = phase_three_fixture(
        visibility=Event.Visibility.INVITE_ONLY
    )

    with pytest.raises(RegistrationUnavailable):
        save_public_response(
            site=site,
            occurrence=occurrence,
            response=Registration.Response.GOING,
            first_name="Alex",
            last_name="Dancer",
            email="alex@example.com",
            guests=[],
        )

    assert not Registration.objects.exists()
    assert not Contact.objects.filter(normalized_email="alex@example.com").exists()


@pytest.mark.django_db
def test_response_change_preserves_history_and_releases_capacity():
    _, site, _, occurrence = phase_three_fixture(capacity=2, max_guests=1)
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    registration, _ = save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        guests=[{"first_name": "Sam", "last_name": "Guest"}],
        source=Registration.Source.MANAGER,
    )

    save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.MAYBE,
        guests=[],
        source=Registration.Source.MANAGER,
    )

    registration.refresh_from_db()
    assert registration.response == Registration.Response.MAYBE
    assert registration.history.count() == 2
    assert (
        registration.participants.filter(status=Participant.Status.ACTIVE).count() == 0
    )
    assert (
        registration.participants.filter(status=Participant.Status.CANCELED).count()
        == 2
    )


@pytest.mark.django_db
def test_capacity_counts_primary_attendees_and_named_guests():
    _, site, _, occurrence = phase_three_fixture(capacity=2, max_guests=1)
    first = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    second = Contact.objects.create(
        site=site, first_name="Jo", last_name="Dancer", email="jo@example.com"
    )
    save_response(
        occurrence=occurrence,
        contact=first,
        response=Registration.Response.GOING,
        guests=[{"first_name": "Sam", "last_name": "Guest"}],
        source=Registration.Source.MANAGER,
    )

    with pytest.raises(CapacityExceeded):
        save_response(
            occurrence=occurrence,
            contact=second,
            response=Registration.Response.GOING,
            guests=[],
            source=Registration.Source.MANAGER,
        )

    assert Participant.objects.filter(status=Participant.Status.ACTIVE).count() == 2


@pytest.mark.django_db
def test_every_guest_requires_first_and_last_name_even_through_internal_service():
    _, site, _, occurrence = phase_three_fixture(capacity=5, max_guests=1)
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )

    with pytest.raises(RegistrationUnavailable, match="every guest"):
        save_response(
            occurrence=occurrence,
            contact=contact,
            response=Registration.Response.GOING,
            guests=[{"first_name": "Sam", "last_name": ""}],
            source=Registration.Source.MANAGER,
        )

    assert not Registration.objects.exists()


@pytest.mark.django_db
def test_public_response_creates_contact_participants_and_confirmation(client):
    _, site, event, occurrence = phase_three_fixture(capacity=5, max_guests=1)
    response = client.post(
        reverse(
            "events:public_response",
            kwargs={"slug": event.slug, "occurrence_id": occurrence.id},
        ),
        {
            "response": "going",
            "first_name": "Alex",
            "last_name": "Dancer",
            "email": "ALEX@example.com",
            "guest_count": "1",
            "guest_1_first_name": "Sam",
            "guest_1_last_name": "Guest",
            "guest_1_email": "",
            "guest_1_phone": "",
        },
        headers={"host": "boot-scooters.localhost"},
    )

    registration = Registration.objects.get(
        occurrence=occurrence, contact__normalized_email="alex@example.com"
    )
    assert response.status_code == 200
    assert "A confirmation email is being sent" in response.content.decode()
    assert "queued" not in response.content.decode().lower()
    assert (
        registration.participants.filter(status=Participant.Status.ACTIVE).count() == 2
    )
    message = OutboundMessage.objects.get(kind=OutboundMessage.Kind.CONFIRMATION)
    assert message.registration == registration
    assert "Alex Dancer" in message.body
    assert "Sam Guest" in message.body
    assert "Manage your response: https://boot-scooters.localhost" in message.body
    assert "An evening of country line dancing." in message.html_body
    assert "going!" in message.html_body
    assert "Manage your response" in message.html_body


@pytest.mark.django_db
def test_public_rsvp_needs_no_account_and_existing_response_uses_secure_link(client):
    _, site, event, occurrence = phase_three_fixture(capacity=5, max_guests=1)
    response_url = reverse(
        "events:public_response",
        kwargs={"slug": event.slug, "occurrence_id": occurrence.id},
    )
    public_page = client.get(
        response_url,
        headers={"host": "boot-scooters.localhost"},
    )
    initial = client.post(
        response_url,
        {
            "response": "going",
            "first_name": "Alex",
            "last_name": "Dancer",
            "email": "alex@example.com",
            "guest_count": "0",
        },
        headers={"host": "boot-scooters.localhost"},
    )
    registration = Registration.objects.get(occurrence=occurrence)

    unsigned_change = client.post(
        response_url,
        {
            "response": "not_going",
            "first_name": "Changed",
            "last_name": "Name",
            "email": "alex@example.com",
            "guest_count": "0",
        },
        headers={"host": "boot-scooters.localhost"},
    )
    registration.refresh_from_db()
    assert registration.response == Registration.Response.GOING
    assert registration.contact.first_name == "Alex"

    manage_token = public_rsvp_manage_token(registration)
    manage_url = reverse(
        "events:public_response_manage",
        kwargs={
            "slug": event.slug,
            "occurrence_id": occurrence.id,
            "token": manage_token,
        },
    )
    manage_page = client.get(
        manage_url,
        headers={"host": "boot-scooters.localhost"},
    )
    secure_change = client.post(
        manage_url,
        {"response": "not_going", "guest_count": "0"},
        headers={"host": "boot-scooters.localhost"},
    )
    registration.refresh_from_db()

    assert public_page.status_code == 200
    assert "No account required" in public_page.content.decode()
    assert initial.status_code == 200
    assert unsigned_change.status_code == 200
    assert "Check your email" in unsigned_change.content.decode()
    assert manage_page.status_code == 200
    assert "Manage your response" in manage_page.content.decode()
    assert secure_change.status_code == 200
    assert registration.response == Registration.Response.NOT_GOING
    assert registration.contact.first_name == "Alex"
    manage_message = OutboundMessage.objects.get(
        registration=registration,
        subject=f"Manage your RSVP: {event.title}",
    )
    assert (
        f"/events/{event.slug}/{occurrence.id}/respond/manage/" in manage_message.body
    )
    tampered_token = ("x" if manage_token[0] != "x" else "y") + manage_token[1:]
    assert (
        client.get(
            reverse(
                "events:public_response_manage",
                kwargs={
                    "slug": event.slug,
                    "occurrence_id": occurrence.id,
                    "token": tampered_token,
                },
            ),
            headers={"host": "boot-scooters.localhost"},
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_public_manage_request_supports_manager_entered_response(client):
    _, site, event, occurrence = phase_three_fixture(capacity=5, max_guests=0)
    contact = Contact.objects.create(
        site=site,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
    )
    registration, _ = save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        guests=[],
        source=Registration.Source.MANAGER,
    )
    response = client.post(
        reverse(
            "events:public_response",
            kwargs={"slug": event.slug, "occurrence_id": occurrence.id},
        ),
        {
            "response": "maybe",
            "first_name": "Alex",
            "last_name": "Dancer",
            "email": "alex@example.com",
            "guest_count": "0",
        },
        headers={"host": "boot-scooters.localhost"},
    )
    manage_message = OutboundMessage.objects.get(
        registration=registration,
        subject=f"Manage your RSVP: {event.title}",
    )
    emailed_url = manage_message.body.split("secure link:\n\n", 1)[1].splitlines()[0]
    manage_url = urlsplit(emailed_url).path

    registration.refresh_from_db()
    assert response.status_code == 200
    assert "Check your email" in response.content.decode()
    assert registration.response == Registration.Response.GOING
    assert manage_url in manage_message.body
    assert (
        client.get(
            manage_url,
            headers={"host": "boot-scooters.localhost"},
        ).status_code
        == 200
    )


@pytest.mark.django_db
def test_confirmation_dedupes_by_registration_history():
    _, site, _, occurrence = phase_three_fixture()
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    registration, history = save_response(
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        guests=[],
        source=Registration.Source.MANAGER,
    )

    first = queue_confirmation(registration, history)
    second = queue_confirmation(registration, history)

    assert first == second
    assert (
        OutboundMessage.objects.filter(kind=OutboundMessage.Kind.CONFIRMATION).count()
        == 1
    )
    assert "Manage your response:" not in first.body


@pytest.mark.django_db
def test_manager_invitation_queues_secure_link_for_invite_only_event(client):
    owner, site, event, occurrence = phase_three_fixture(
        visibility=Event.Visibility.INVITE_ONLY
    )
    contact = Contact.objects.create(
        site=site, first_name="Alex", last_name="Dancer", email="alex@example.com"
    )
    site.theme.logo.name = "site-logos/brand.png"
    site.theme.hero_image.name = "site-heroes/dance.jpg"
    site.theme.save(update_fields=("logo", "hero_image", "updated_at"))
    event.featured_image.name = "event-images/friday-dance.jpg"
    event.save(update_fields=("featured_image", "updated_at"))
    client.force_login(owner)
    invitation_url = reverse(
        "events:invite",
        kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
    )
    form_page = client.get(invitation_url)

    response = client.post(
        invitation_url,
        {"contacts": [str(contact.id)]},
        follow=True,
    )

    invitation = Invitation.objects.get(contact=contact, occurrence=occurrence)
    message = OutboundMessage.objects.get(kind=OutboundMessage.Kind.INVITATION)
    token = message.body.split("/invitations/", 1)[1].split("/", 1)[0]
    invite_page = client.get(
        reverse("events:invitation_response", kwargs={"token": token}),
        headers={"host": "boot-scooters.localhost"},
    )
    direct_page = client.get(
        reverse(
            "events:occurrence_detail",
            kwargs={"slug": event.slug, "occurrence_id": occurrence.id},
        ),
        headers={"host": "boot-scooters.localhost"},
    )

    assert form_page.status_code == 200
    assert "Send invitations" in form_page.content.decode()
    assert "Allow up to 10 minutes" in form_page.content.decode()
    assert response.status_code == 200
    assert "Invitation is being sent to 1 person." in response.content.decode()
    assert "allow up to 10 minutes" in response.content.decode()
    assert "An evening of country line dancing." in message.body
    assert "An evening of country line dancing." in message.html_body
    assert "View invitation and RSVP" in message.html_body
    assert (
        "https://boot-scooters.localhost/events/friday-dance/image/?v="
        in message.html_body
    )
    assert "https://boot-scooters.localhost/branding/logo/?v=" in message.html_body
    assert invitation.token_hash != token
    assert invite_page.status_code == 200
    assert "Friday dance" in invite_page.content.decode()
    assert direct_page.status_code == 404


@pytest.mark.django_db
def test_event_cancellation_sends_notices_for_affected_responses(client):
    owner, site, event, occurrence = phase_three_fixture()
    going = Contact.objects.create(
        site=site, first_name="Alex", last_name="Going", email="going@example.com"
    )
    declining = Contact.objects.create(
        site=site,
        first_name="Jo",
        last_name="Declining",
        email="declining@example.com",
    )
    for contact, response_value in (
        (going, Registration.Response.GOING),
        (declining, Registration.Response.NOT_GOING),
    ):
        save_response(
            occurrence=occurrence,
            contact=contact,
            response=response_value,
            guests=[],
            source=Registration.Source.MANAGER,
        )
    client.force_login(owner)

    response = client.post(
        reverse("events:cancel", kwargs={"site_id": site.id, "event_id": event.id}),
        follow=True,
    )

    event.refresh_from_db()
    occurrence.refresh_from_db()
    cancellation_messages = OutboundMessage.objects.filter(
        kind=OutboundMessage.Kind.CANCELLATION
    )
    assert response.status_code == 200
    assert "Notices are being sent to affected attendees." in response.content.decode()
    assert event.status == Event.Status.CANCELED
    assert occurrence.status == occurrence.Status.CANCELED
    assert list(cancellation_messages.values_list("recipient_email", flat=True)) == [
        "going@example.com"
    ]


@pytest.mark.django_db(transaction=True)
def test_postgresql_occurrence_lock_prevents_capacity_oversell():
    from django.db import connection

    if connection.vendor != "postgresql":
        pytest.skip("Authoritative concurrency assertion runs in PostgreSQL CI.")
    _, site, _, occurrence = phase_three_fixture(capacity=1, max_guests=0)
    contacts = [
        Contact.objects.create(
            site=site,
            first_name=f"Person{index}",
            last_name="Dancer",
            email=f"person{index}@example.com",
        )
        for index in range(2)
    ]

    def respond(contact_id):
        connections.close_all()
        contact = Contact.objects.get(pk=contact_id)
        current_occurrence = occurrence.__class__.objects.get(pk=occurrence.pk)
        try:
            save_response(
                occurrence=current_occurrence,
                contact=contact,
                response=Registration.Response.GOING,
                guests=[],
                source=Registration.Source.MANAGER,
            )
        except CapacityExceeded:
            return "full"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(respond, [contact.id for contact in contacts]))

    assert sorted(outcomes) == ["full", "saved"]
    assert Participant.objects.filter(status=Participant.Status.ACTIVE).count() == 1
