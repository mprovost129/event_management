import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from contacts.models import ConsentStatus, Contact
from contacts.services import replace_contact_tags, subscribe_to_newsletter
from sites.services import create_subscriber_site
from users.models import User


def create_site(slug, email):
    owner = User.objects.create_user(
        email=email,
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    return create_subscriber_site(
        owner=owner,
        display_name=slug,
        slug=slug,
        timezone_name="America/New_York",
    )


@pytest.mark.django_db
def test_normalized_email_is_unique_within_site_but_allowed_across_sites():
    first = create_site("first-group", "first-owner@example.com")
    second = create_site("second-group", "second-owner@example.com")
    Contact.objects.create(
        site=first, first_name="Pat", last_name="One", email="Pat@Example.com"
    )
    Contact.objects.create(
        site=second, first_name="Pat", last_name="Two", email="pat@example.com"
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        Contact.objects.create(
            site=first,
            first_name="Duplicate",
            last_name="Person",
            email="PAT@example.com",
        )


@pytest.mark.django_db
def test_newsletter_signup_does_not_overwrite_manager_notes():
    site = create_site("first-group", "owner@example.com")
    contact = Contact.objects.create(
        site=site,
        first_name="Pat",
        last_name="Dancer",
        email="pat@example.com",
        notes="Prefers beginner events.",
    )

    subscribe_to_newsletter(
        site=site,
        email="PAT@example.com",
        first_name="Different",
        last_name="Name",
        source="public_newsletter_form",
    )

    contact.refresh_from_db()
    assert contact.first_name == "Pat"
    assert contact.notes == "Prefers beginner events."
    assert contact.email_consent_status == ConsentStatus.GRANTED


@pytest.mark.django_db
def test_contact_tags_are_scoped_to_the_contact_site():
    first = create_site("first-group", "first-owner@example.com")
    second = create_site("second-group", "second-owner@example.com")
    first_contact = Contact.objects.create(site=first, first_name="A", last_name="One")
    second_contact = Contact.objects.create(
        site=second, first_name="B", last_name="Two"
    )

    replace_contact_tags(first_contact, ["Beginner"])
    replace_contact_tags(second_contact, ["Beginner"])

    assert first_contact.tags.get().site == first
    assert second_contact.tags.get().site == second
    assert first_contact.tags.get().pk != second_contact.tags.get().pk
