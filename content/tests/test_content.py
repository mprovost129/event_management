from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from contacts.models import ConsentRecord, ConsentStatus, Contact
from content.images import prepare_image
from content.models import BlogPost, PublishingStatus, SitePage
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
def test_site_creation_initializes_fixed_page_types():
    _, site = create_site()

    assert set(SitePage.objects.for_site(site).values_list("page_type", flat=True)) == {
        SitePage.PageType.HOME,
        SitePage.PageType.ABOUT,
        SitePage.PageType.CONTACT,
        SitePage.PageType.NEWSLETTER,
    }


@pytest.mark.django_db
def test_published_blog_is_visible_only_on_its_site(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    BlogPost.objects.create(
        site=site,
        title="Dance night update",
        slug="dance-night-update",
        excerpt="New details",
        body="Bring your dancing shoes.",
        status=PublishingStatus.PUBLISHED,
        publish_at=timezone.now(),
    )

    response = client.get(
        reverse("content:blog_index"), headers={"host": "boot-scooters.localhost"}
    )
    control_host = client.get(reverse("content:blog_index"))

    assert response.status_code == 200
    assert "Dance night update" in response.content.decode()
    assert control_host.status_code == 404


@pytest.mark.django_db
def test_newsletter_signup_creates_contact_and_consent_history(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))

    response = client.post(
        reverse("content:newsletter"),
        {
            "first_name": "Pat",
            "last_name": "Dancer",
            "email": "PAT@EXAMPLE.COM",
            "consent": "on",
        },
        headers={"host": "boot-scooters.localhost"},
    )

    contact = Contact.objects.get(site=site, normalized_email="pat@example.com")
    assert response.status_code == 302
    assert contact.email_consent_status == ConsentStatus.GRANTED
    assert ConsentRecord.objects.filter(
        site=site,
        contact=contact,
        channel=ConsentRecord.Channel.EMAIL,
        status=ConsentStatus.GRANTED,
        source="public_newsletter_form",
    ).exists()


@pytest.mark.django_db
def test_draft_page_is_not_public(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    about = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    about.body = "About our group"
    about.save(update_fields=("body", "updated_at"))

    response = client.get(
        reverse("content:about"), headers={"host": "boot-scooters.localhost"}
    )

    assert response.status_code == 404


def test_uploaded_images_are_validated_and_resized():
    source = BytesIO()
    Image.new("RGB", (3000, 1200), color="navy").save(source, format="JPEG")
    upload = SimpleUploadedFile(
        "hero.jpg", source.getvalue(), content_type="image/jpeg"
    )

    prepared = prepare_image(upload, max_dimension=1200)
    resized = Image.open(prepared)

    assert max(resized.size) == 1200
    assert resized.format == "JPEG"
