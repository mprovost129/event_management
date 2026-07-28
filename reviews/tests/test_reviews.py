from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from attendance.services import set_check_in
from communications.models import OutboundMessage
from contacts.models import Contact
from events.models import Event, EventOccurrence, Participant, Registration
from ops.models import AuditEvent
from reviews.models import Review, ReviewModeration
from reviews.services import (
    moderate_review,
    participant_can_review,
    queue_due_review_requests,
    report_review,
    review_token,
    save_review,
)
from sites.services import create_subscriber_site
from users.models import User


def review_fixture(*, ended=True, checked_in=True):
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
    end = (
        timezone.now() - timedelta(hours=1)
        if ended
        else timezone.now() + timedelta(hours=2)
    )
    event = Event.objects.create(
        site=site,
        title="Friday dance",
        slug="friday-dance",
        status=Event.Status.PUBLISHED,
    )
    occurrence = EventOccurrence.objects.create(
        site=site,
        event=event,
        starts_at=end - timedelta(hours=2),
        ends_at=end,
        timezone=site.timezone,
    )
    contact = Contact.objects.create(
        site=site,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
    )
    registration = Registration.objects.create(
        site=site,
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        source=Registration.Source.MANAGER,
    )
    participant = Participant.objects.create(
        site=site,
        registration=registration,
        first_name="Alex",
        last_name="Dancer",
        email="alex@example.com",
        is_primary=True,
    )
    if checked_in:
        set_check_in(participant=participant, actor=owner, checked_in=True)
    return owner, site, occurrence, participant


@pytest.mark.django_db
def test_only_checked_in_attendees_can_review_after_event():
    owner, _, occurrence, participant = review_fixture(checked_in=False)
    assert participant_can_review(participant) is False
    with pytest.raises(ValidationError):
        save_review(participant=participant, rating=5, comment="Great")

    set_check_in(participant=participant, actor=owner, checked_in=True)
    occurrence.ends_at = timezone.now() + timedelta(hours=2)
    occurrence.save(update_fields=("ends_at", "updated_at"))
    participant.registration.occurrence = occurrence
    assert participant_can_review(participant) is False
    with pytest.raises(ValidationError):
        save_review(participant=participant, rating=5, comment="Too early")


@pytest.mark.django_db
def test_review_capability_supports_submit_edit_and_soft_delete():
    _, site, _, participant = review_fixture()
    client = Client(HTTP_HOST="boot-scooters.localhost")
    url = reverse("reviews:submit", kwargs={"token": review_token(participant)})

    response = client.post(url, {"rating": 4, "comment": "Fun evening"})
    assert response.status_code == 200
    review = Review.objects.get(participant=participant)
    assert review.display_name == "Alex Dancer"
    assert review.edited_at is None

    client.post(url, {"rating": 5, "comment": "Even better than I remembered"})
    review.refresh_from_db()
    assert Review.objects.filter(participant=participant).count() == 1
    assert review.rating == 5
    assert review.edited_at is not None

    client.post(url, {"action": "delete"})
    review.refresh_from_db()
    assert review.deleted_at is not None
    assert review.comment == ""
    assert review.is_public is False


@pytest.mark.django_db
def test_review_request_queue_is_deduplicated():
    _, site, _, participant = review_fixture()

    assert queue_due_review_requests() == 1
    assert queue_due_review_requests() == 0
    message = OutboundMessage.objects.get(kind=OutboundMessage.Kind.REVIEW_REQUEST)
    assert message.recipient_email == participant.email
    assert "https://boot-scooters.localhost/reviews/" in message.body
    assert message.site == site


@pytest.mark.django_db
def test_staff_report_does_not_hide_review_but_platform_moderation_does():
    owner, site, _, participant = review_fixture()
    review, _ = save_review(participant=participant, rating=1, comment="Not for me")

    report_review(review=review, actor=owner, reason="Potentially abusive")
    review.refresh_from_db()
    assert review.moderation_status == Review.ModerationStatus.REPORTED
    assert review.is_public is True

    platform_admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    moderate_review(
        review=review,
        actor=platform_admin,
        action=ReviewModeration.Action.HIDDEN,
        reason="Contains personal information",
    )
    review.refresh_from_db()
    assert review.is_public is False
    assert AuditEvent.objects.filter(
        action="review.moderated.hidden", site_id=site.id
    ).exists()

    moderate_review(
        review=review,
        actor=platform_admin,
        action=ReviewModeration.Action.RESTORED,
        reason="Personal information removed",
    )
    review.refresh_from_db()
    assert review.is_public is True
    assert list(review.moderation_history.values_list("action", flat=True)) == [
        ReviewModeration.Action.RESTORED,
        ReviewModeration.Action.HIDDEN,
    ]


@pytest.mark.django_db
def test_review_token_is_site_bound():
    _, _, _, participant = review_fixture()
    other_owner = User.objects.create_user(
        email="other@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    create_subscriber_site(
        owner=other_owner,
        display_name="Other Group",
        slug="other-group",
        timezone_name="America/New_York",
    )
    response = Client(HTTP_HOST="other-group.localhost").get(
        reverse("reviews:submit", kwargs={"token": review_token(participant)})
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_public_rating_and_subscriber_response_only_include_visible_reviews():
    owner, site, occurrence, participant = review_fixture()
    review, _ = save_review(participant=participant, rating=4, comment="Friendly crowd")
    staff_client = Client()
    staff_client.force_login(owner)
    response_url = reverse(
        "reviews:respond", kwargs={"site_id": site.id, "review_id": review.id}
    )
    assert (
        staff_client.post(response_url, {"response": "Thanks for coming!"}).status_code
        == 302
    )

    public_client = Client(HTTP_HOST="boot-scooters.localhost")
    detail_url = reverse(
        "events:occurrence_detail",
        kwargs={"slug": occurrence.event.slug, "occurrence_id": occurrence.id},
    )
    response = public_client.get(detail_url)
    assert response.status_code == 200
    assert b"4.0/5" in response.content
    assert b"Friendly crowd" in response.content
    assert b"Thanks for coming!" in response.content

    platform_admin = User.objects.create_superuser(
        email="admin@example.com", password="Strong-Test-Pass-2026!"
    )
    moderate_review(
        review=review,
        actor=platform_admin,
        action=ReviewModeration.Action.HIDDEN,
        reason="Privacy concern",
    )
    response = public_client.get(detail_url)
    assert b"Friendly crowd" not in response.content
    assert b"Attendee reviews" not in response.content
