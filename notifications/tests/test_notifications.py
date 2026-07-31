import pytest
from django.urls import reverse
from django.utils import timezone

from notifications.models import Notification
from notifications.services import notify_site_staff
from sites.services import create_subscriber_site
from users.models import User


def create_site(slug, email):
    owner = User.objects.create_user(
        email=email,
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name=slug,
        slug=slug,
        timezone_name="America/New_York",
    )
    return site, owner


@pytest.mark.django_db
def test_notifications_without_dedupe_keys_are_each_created():
    site, owner = create_site("first-group", "owner@example.com")

    first = notify_site_staff(
        site=site,
        kind=Notification.Kind.SYSTEM,
        title="First",
        message="First update",
        email=False,
    )
    second = notify_site_staff(
        site=site,
        kind=Notification.Kind.SYSTEM,
        title="Second",
        message="Second update",
        email=False,
    )

    assert len(first) == len(second) == 1
    assert owner.notifications.count() == 2


@pytest.mark.django_db
def test_notification_dedupe_key_is_idempotent_per_recipient():
    site, owner = create_site("first-group", "owner@example.com")

    for _ in range(2):
        notify_site_staff(
            site=site,
            kind=Notification.Kind.SYSTEM,
            title="Import completed",
            message="The import is ready.",
            dedupe_key="import:123",
            email=False,
        )

    assert owner.notifications.count() == 1


@pytest.mark.django_db
def test_notification_views_never_read_another_users_notification(client):
    first_site, first_owner = create_site("first-group", "first@example.com")
    second_site, second_owner = create_site("second-group", "second@example.com")
    first_notification = Notification.objects.create(
        recipient=first_owner,
        site=first_site,
        kind=Notification.Kind.SYSTEM,
        title="First only",
        message="Visible to the first owner.",
    )
    second_notification = Notification.objects.create(
        recipient=second_owner,
        site=second_site,
        kind=Notification.Kind.SYSTEM,
        title="Second only",
        message="Visible to the second owner.",
    )
    client.force_login(first_owner)

    listing = client.get(reverse("notifications:list"))
    denied = client.post(
        reverse("notifications:mark_read", args=(second_notification.id,))
    )
    marked = client.post(
        reverse("notifications:mark_read", args=(first_notification.id,))
    )

    assert listing.status_code == 200
    assert "First only" in listing.content.decode()
    assert "Second only" not in listing.content.decode()
    assert denied.status_code == 404
    assert marked.status_code == 302
    first_notification.refresh_from_db()
    second_notification.refresh_from_db()
    assert first_notification.read_at is not None
    assert second_notification.read_at is None


@pytest.mark.django_db
def test_notifications_page_shows_empty_state_without_mark_all_action(client):
    site, owner = create_site("empty-group", "empty-owner@example.com")
    client.force_login(owner)

    response = client.get(reverse("notifications:list"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "No notifications yet." in content
    assert "Mark all read" not in content


@pytest.mark.django_db
def test_notifications_page_shows_mark_all_read_for_unread_items(client):
    site, owner = create_site("alert-group", "alert-owner@example.com")
    Notification.objects.create(
        recipient=owner,
        site=site,
        kind=Notification.Kind.SYSTEM,
        title="Action required",
        message="Please review your latest update.",
    )
    client.force_login(owner)

    response = client.get(reverse("notifications:list"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Action required" in content
    assert "Mark all read" in content
