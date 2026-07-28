import re
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from communications.models import OutboundMessage
from contacts.models import Contact
from events.models import Event, Invitation, Participant, Registration
from reviews.models import Review
from reviews.services import review_token
from sites.models import Site
from users.models import User


@pytest.mark.django_db
def test_primary_free_event_journey_from_onboarding_through_review_and_reports(client):
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    client.force_login(owner)
    onboarding = client.post(
        reverse("sites:onboarding"),
        {
            "display_name": "Boot Scooters",
            "slug": "boot-scooters",
            "timezone": "America/New_York",
            "template_key": "classic",
        },
    )
    site = Site.objects.get(slug="boot-scooters")
    assert onboarding.status_code == 302
    assert site.platform_subscription.status == "trialing"

    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    starts_at = (timezone.now() + timedelta(days=7)).astimezone(ZoneInfo(site.timezone))
    create_event = client.post(
        reverse("events:create", kwargs={"site_id": site.id}),
        {
            "title": "Friday dance",
            "slug": "friday-dance",
            "description": "An evening of country line dancing.",
            "host_name": "Pat",
            "visibility": "invite_only",
            "status": "published",
            "recurrence": "none",
            "recurrence_interval": "1",
            "recurrence_until": "",
            "max_guests": "1",
            "start_date": starts_at.date().isoformat(),
            "start_time": starts_at.strftime("%H:%M"),
            "end_date": (starts_at + timedelta(hours=2)).date().isoformat(),
            "end_time": (starts_at + timedelta(hours=2)).strftime("%H:%M"),
            "venue_name": "Town Hall",
            "venue_address": "100 Main Street",
            "capacity": "20",
        },
    )
    assert create_event.status_code == 302, create_event.context[
        "form"
    ].errors.as_json()
    event = Event.objects.get(site=site, slug="friday-dance")
    occurrence = event.occurrences.get()

    contact = Contact.objects.create(
        site=site,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
    )
    invited = client.post(
        reverse(
            "events:invite",
            kwargs={"site_id": site.id, "occurrence_id": occurrence.id},
        ),
        {"contacts": [str(contact.id)]},
    )
    invitation = Invitation.objects.get(occurrence=occurrence, contact=contact)
    message = OutboundMessage.objects.get(kind=OutboundMessage.Kind.INVITATION)
    token = re.search(r"/invitations/([^/]+)/", message.body).group(1)
    assert invited.status_code == 302

    response = client.post(
        reverse("events:invitation_response", kwargs={"token": token}),
        {
            "response": "going",
            "guest_count": "1",
            "guest_1_first_name": "Sam",
            "guest_1_last_name": "Guest",
            "guest_1_email": "",
            "guest_1_phone": "",
        },
        headers={"host": "boot-scooters.localhost"},
    )
    registration = Registration.objects.get(occurrence=occurrence, contact=contact)
    participants = list(registration.participants.order_by("-is_primary"))
    invitation.refresh_from_db()
    assert response.status_code == 200
    assert invitation.status == Invitation.Status.RESPONDED
    assert registration.response == Registration.Response.GOING
    assert [participant.display_name for participant in participants] == [
        "Alex Dancer",
        "Sam Guest",
    ]

    primary = next(
        participant for participant in participants if participant.is_primary
    )
    checked_in = client.post(
        reverse(
            "attendance:toggle",
            kwargs={
                "site_id": site.id,
                "occurrence_id": occurrence.id,
                "participant_id": primary.id,
            },
        ),
        {"action": "check_in"},
    )
    primary.refresh_from_db()
    assert checked_in.status_code == 302
    assert primary.attendance_status.checked_in_at is not None

    occurrence.starts_at = timezone.now() - timedelta(hours=3)
    occurrence.ends_at = timezone.now() - timedelta(hours=1)
    occurrence.save(update_fields=("starts_at", "ends_at", "updated_at"))
    review = client.post(
        reverse("reviews:submit", kwargs={"token": review_token(primary)}),
        {"rating": "5", "comment": "Friendly group and a great dance."},
        headers={"host": "boot-scooters.localhost"},
    )
    assert review.status_code == 200
    assert Review.objects.get(participant=primary).rating == 5

    reports = client.get(reverse("sites:reports", kwargs={"site_id": site.id}))
    assert reports.status_code == 200
    assert b"Friday dance" in reports.content
    assert Participant.objects.filter(registration=registration).count() == 2
