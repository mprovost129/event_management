import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from contacts.models import (
    ConsentStatus,
    Contact,
    Member,
    MembershipPlan,
    MemberSubscription,
)
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


@pytest.mark.django_db
def test_manager_can_add_contact_as_member_without_inventing_consent(client):
    site = create_site("first-group", "owner@example.com")
    owner = User.objects.get(email="owner@example.com")
    client.force_login(owner)

    response = client.post(
        reverse("contacts:create", args=(site.id,)),
        {
            "first_name": "Pat",
            "last_name": "Dancer",
            "email": "pat@example.com",
            "phone": "+15551234567",
            "notes": "Prefers beginner dances.",
            "tag_names": "Beginner, Volunteer",
            "member_tracking": "active",
            "member_starts_on": "2026-07-01",
            "member_ends_on": "",
            "member_notes": "Pays dues offline.",
        },
    )

    contact = Contact.objects.get(email="pat@example.com")
    member = Member.objects.get(contact=contact)
    assert response.status_code == 302
    assert response.url.endswith(f"?created={contact.id}")
    assert member.administrative_status == Member.AdministrativeStatus.ACTIVE
    assert member.notes == "Pays dues offline."
    assert contact.email_consent_status == ConsentStatus.UNKNOWN
    assert contact.sms_consent_status == ConsentStatus.UNKNOWN
    assert set(contact.tags.values_list("name", flat=True)) == {
        "Beginner",
        "Volunteer",
    }

    followup = client.get(response.url)
    content = followup.content.decode()
    assert "Active member" in content
    assert "Email Unknown" in content


@pytest.mark.django_db
def test_member_with_subscription_history_cannot_be_changed_to_contact_only(client):
    site = create_site("first-group", "owner@example.com")
    owner = User.objects.get(email="owner@example.com")
    contact = Contact.objects.create(
        site=site,
        first_name="Pat",
        last_name="Dancer",
        email="pat@example.com",
    )
    member = Member.objects.create(site=site, contact=contact)
    plan = MembershipPlan.objects.create(
        site=site,
        name="Annual member",
        amount_cents=10000,
        currency="usd",
        interval=MembershipPlan.Interval.YEARLY,
    )
    MemberSubscription.objects.create(
        site=site,
        member=member,
        plan=plan,
        status=MemberSubscription.Status.ACTIVE,
        connected_account_id="acct_site",
    )
    client.force_login(owner)

    response = client.post(
        reverse("contacts:edit", args=(site.id, contact.id)),
        {
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "email": contact.email,
            "phone": "",
            "notes": "",
            "tag_names": "",
            "member_tracking": "contact_only",
            "member_starts_on": "",
            "member_ends_on": "",
            "member_notes": "",
        },
    )

    assert response.status_code == 200
    assert "Mark them inactive instead" in response.content.decode()
    assert Member.objects.filter(pk=member.pk).exists()
    assert 'id="archive-contact-form"' in response.content.decode()
    assert 'data-confirm="Archive this contact?' in response.content.decode()
