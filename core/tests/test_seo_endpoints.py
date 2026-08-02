from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from content.models import BlogPost, PublishingStatus, SitePage
from events.models import Event, EventOccurrence
from sites.services import create_subscriber_site
from users.models import User


def create_site(slug="boot-scooters"):
    owner = User.objects.create_user(
        email=f"{slug}@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="Boot Scooters",
        slug=slug,
        timezone_name="America/New_York",
    )
    return owner, site


@pytest.mark.django_db
def test_robots_txt_on_control_host_includes_sitemap(client):
    response = client.get(reverse("core:robots"), headers={"host": "localhost"})

    content = response.content.decode()
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    assert "User-agent: *" in content
    assert "Allow: /" in content
    assert "Sitemap: http://localhost/sitemap.xml" in content


@pytest.mark.django_db
def test_robots_txt_on_published_tenant_host_includes_tenant_sitemap(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))

    response = client.get(
        reverse("core:robots"),
        headers={"host": f"{site.slug}.localhost"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Allow: /" in content
    assert f"Sitemap: http://{site.slug}.localhost/sitemap.xml" in content


@pytest.mark.django_db
def test_sitemap_on_control_host_lists_core_pages(client):
    response = client.get(reverse("core:sitemap"), headers={"host": "localhost"})

    content = response.content.decode()
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    assert "<urlset" in content
    assert "http://localhost/" in content
    assert "http://localhost/help/" in content
    assert "http://localhost/legal/" in content


@pytest.mark.django_db
def test_sitemap_on_tenant_host_lists_only_public_resources(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))

    about = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    about.status = PublishingStatus.PUBLISHED
    about.publish_at = timezone.now() - timedelta(minutes=5)
    about.body = "About our group"
    about.save(update_fields=("status", "publish_at", "body", "updated_at"))

    contact = SitePage.objects.get(site=site, page_type=SitePage.PageType.CONTACT)
    contact.status = PublishingStatus.DRAFT
    contact.save(update_fields=("status", "updated_at"))

    BlogPost.objects.create(
        site=site,
        title="Dance night update",
        slug="dance-night-update",
        excerpt="New details",
        body="Bring your dancing shoes.",
        status=PublishingStatus.PUBLISHED,
        publish_at=timezone.now() - timedelta(minutes=2),
    )

    event = Event.objects.create(
        site=site,
        title="Friday dance",
        slug="friday-dance",
        visibility=Event.Visibility.PUBLIC,
        status=Event.Status.PUBLISHED,
    )
    starts_at = timezone.now() + timedelta(days=3)
    occurrence = EventOccurrence.objects.create(
        site=site,
        event=event,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        timezone=site.timezone,
        status=EventOccurrence.Status.SCHEDULED,
    )

    private_event = Event.objects.create(
        site=site,
        title="Invite-only dance",
        slug="invite-only-dance",
        visibility=Event.Visibility.INVITE_ONLY,
        status=Event.Status.PUBLISHED,
    )
    EventOccurrence.objects.create(
        site=site,
        event=private_event,
        starts_at=starts_at + timedelta(days=1),
        ends_at=starts_at + timedelta(days=1, hours=2),
        timezone=site.timezone,
        status=EventOccurrence.Status.SCHEDULED,
    )

    response = client.get(
        reverse("core:sitemap"),
        headers={"host": f"{site.slug}.localhost"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert f"http://{site.slug}.localhost/about/" in content
    assert f"http://{site.slug}.localhost/contact/" not in content
    assert f"http://{site.slug}.localhost/blog/dance-night-update/" in content
    assert f"http://{site.slug}.localhost/events/{event.slug}/" in content
    assert (
        f"http://{site.slug}.localhost/events/{event.slug}/{occurrence.id}/" in content
    )
    assert f"http://{site.slug}.localhost/events/{private_event.slug}/" not in content
