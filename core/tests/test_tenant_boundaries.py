from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from communications.models import Campaign
from contacts.models import Contact, MembershipPlan
from content.models import BlogPost
from events.models import Event, EventOccurrence, Participant, Registration
from payments.models import Order, TicketType
from reviews.models import Review
from sites.services import create_subscriber_site
from users.models import User


def _tenant_fixture():
    owner = User.objects.create_user(
        email="owner@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    other_owner = User.objects.create_user(
        email="other@example.com",
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    site = create_subscriber_site(
        owner=owner,
        display_name="First Site",
        slug="first-site",
        timezone_name="America/New_York",
    )
    other_site = create_subscriber_site(
        owner=other_owner,
        display_name="Other Site",
        slug="other-site",
        timezone_name="America/New_York",
    )
    contact = Contact.objects.create(
        site=other_site,
        first_name="Other",
        last_name="Member",
        email="member@other.example",
    )
    event = Event.objects.create(
        site=other_site,
        title="Other Event",
        slug="other-event",
    )
    starts_at = timezone.now() + timedelta(days=2)
    occurrence = EventOccurrence.objects.create(
        site=other_site,
        event=event,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        timezone=other_site.timezone,
    )
    registration = Registration.objects.create(
        site=other_site,
        occurrence=occurrence,
        contact=contact,
        response=Registration.Response.GOING,
        source=Registration.Source.MANAGER,
    )
    participant = Participant.objects.create(
        site=other_site,
        registration=registration,
        first_name=contact.first_name,
        last_name=contact.last_name,
        email=contact.email,
        is_primary=True,
    )
    review = Review.objects.create(
        site=other_site,
        occurrence=occurrence,
        participant=participant,
        display_name="Other M.",
        rating=5,
    )
    campaign = Campaign.objects.create(
        site=other_site,
        name="Other Campaign",
        subject="News",
        body="Tenant-owned content",
    )
    blog_post = BlogPost.objects.create(
        site=other_site,
        title="Other Post",
        slug="other-post",
        body="Tenant-owned content",
        author=other_owner,
    )
    ticket_type = TicketType.objects.create(
        site=other_site,
        occurrence=occurrence,
        name="Admission",
        amount_cents=1000,
        currency=other_site.currency,
        quantity=20,
    )
    membership_plan = MembershipPlan.objects.create(
        site=other_site,
        name="Other Membership",
        amount_cents=1000,
        currency=other_site.currency,
        interval=MembershipPlan.Interval.MONTHLY,
    )
    order = Order.objects.create(
        site=other_site,
        occurrence=occurrence,
        registration=registration,
        purchaser=contact,
        connected_account_id="acct_other",
        currency=other_site.currency,
        subtotal_cents=1000,
        total_cents=1000,
        status=Order.Status.PAID,
    )
    return {
        "owner": owner,
        "site": site,
        "contact": contact,
        "event": event,
        "occurrence": occurrence,
        "participant": participant,
        "review": review,
        "campaign": campaign,
        "blog_post": blog_post,
        "ticket_type": ticket_type,
        "membership_plan": membership_plan,
        "order": order,
    }


@pytest.mark.django_db
def test_object_endpoints_reject_cross_tenant_identifier_substitution(client):
    objects = _tenant_fixture()
    site = objects["site"]
    client.force_login(objects["owner"])

    get_urls = (
        reverse("contacts:detail", args=(site.id, objects["contact"].id)),
        reverse("contacts:edit", args=(site.id, objects["contact"].id)),
        reverse("content:blog_edit", args=(site.id, objects["blog_post"].id)),
        reverse("events:edit", args=(site.id, objects["event"].id)),
        reverse("events:occurrence_edit", args=(site.id, objects["occurrence"].id)),
        reverse("events:invite", args=(site.id, objects["occurrence"].id)),
        reverse("events:manager_response", args=(site.id, objects["occurrence"].id)),
        reverse("communications:campaign_edit", args=(site.id, objects["campaign"].id)),
        reverse(
            "communications:campaign_preview",
            args=(site.id, objects["campaign"].id),
        ),
        reverse(
            "payments:ticket_type_edit",
            args=(site.id, objects["ticket_type"].id),
        ),
        reverse(
            "payments:membership_plan_edit",
            args=(site.id, objects["membership_plan"].id),
        ),
        reverse("reviews:respond", args=(site.id, objects["review"].id)),
        reverse("attendance:roster", args=(site.id, objects["occurrence"].id)),
    )
    for url in get_urls:
        assert client.get(url).status_code == 404, url

    post_urls = (
        reverse("contacts:archive", args=(site.id, objects["contact"].id)),
        reverse("events:cancel", args=(site.id, objects["event"].id)),
        reverse(
            "communications:campaign_duplicate",
            args=(site.id, objects["campaign"].id),
        ),
        reverse("payments:refund_order", args=(site.id, objects["order"].id)),
        reverse("reviews:report", args=(site.id, objects["review"].id)),
        reverse(
            "attendance:toggle",
            args=(site.id, objects["occurrence"].id, objects["participant"].id),
        ),
    )
    for url in post_urls:
        assert client.post(url).status_code == 404, url
