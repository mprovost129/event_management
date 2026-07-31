import pytest
from django.urls import reverse

from notifications.models import Notification
from sites.services import create_subscriber_site
from users.models import User


@pytest.mark.django_db
def test_profile_page_requires_authentication(client):
    response = client.get(reverse("users:profile"))

    assert response.status_code == 302
    assert reverse("users:login") in response.url


@pytest.mark.django_db
def test_authenticated_user_can_update_profile_fields(client):
    user = User.objects.create_user(
        email="member@example.com",
        password="Strong-Test-Pass-2026!",
    )
    client.force_login(user)

    response = client.post(
        reverse("users:profile"),
        {
            "username": "DanceLeader",
            "first_name": "Robin",
            "last_name": "Lane",
            "mailing_address_line1": "123 Main Street",
            "mailing_address_line2": "Suite 6",
            "mailing_city": "Boston",
            "mailing_state": "MA",
            "mailing_postal_code": "02110",
            "mailing_country": "US",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("users:profile")

    user.refresh_from_db()
    assert user.username == "DanceLeader"
    assert user.first_name == "Robin"
    assert user.last_name == "Lane"
    assert user.mailing_address_line1 == "123 Main Street"
    assert user.mailing_address_line2 == "Suite 6"
    assert user.mailing_city == "Boston"
    assert user.mailing_state == "MA"
    assert user.mailing_postal_code == "02110"
    assert user.mailing_country == "US"


@pytest.mark.django_db
def test_authenticated_navbar_includes_profile_help_and_notifications(client):
    user = User.objects.create_user(
        email="member@example.com",
        password="Strong-Test-Pass-2026!",
        first_name="Robin",
    )
    client.force_login(user)

    response = client.get(reverse("sites:account_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert reverse("users:profile") in content
    assert "Notifications" in content
    assert "/help/" in content


@pytest.mark.django_db
def test_authenticated_navbar_notification_dropdown_shows_actions(client):
    user = User.objects.create_user(
        email="member@example.com",
        password="Strong-Test-Pass-2026!",
        first_name="Robin",
        last_name="Lane",
    )
    site = create_subscriber_site(
        owner=user,
        display_name="Boot Scooters",
        slug="boot-scooters-nav-test",
        timezone_name="America/New_York",
    )
    Notification.objects.create(
        recipient=user,
        site=site,
        kind=Notification.Kind.SYSTEM,
        title="Billing reminder",
        message="Your trial ends soon.",
        action_url=reverse("sites:account_dashboard"),
    )
    client.force_login(user)

    response = client.get(reverse("sites:account_dashboard"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Mark all read" in content
    assert "View all" in content
    assert "Billing reminder" in content
    assert "Robin Lane" in content


@pytest.mark.django_db
def test_profile_page_shows_identity_and_mailing_sections(client):
    user = User.objects.create_user(
        email="member@example.com",
        password="Strong-Test-Pass-2026!",
    )
    client.force_login(user)

    response = client.get(reverse("users:profile"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Identity" in content
    assert "Mailing address" in content
    assert "Menu preview" in content
