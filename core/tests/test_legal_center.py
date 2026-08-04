import pytest
from django.urls import reverse

LEGAL_ROUTES = (
    ("core:legal", "Legal center"),
    ("core:terms", "Terms of Service"),
    ("core:privacy", "Privacy Notice"),
    ("core:cookies", "Cookie Notice"),
    ("core:refunds", "Payments, Cancellations &amp; Refunds"),
    ("core:acceptable_use", "Acceptable Use Policy"),
    ("core:retention", "Data Retention &amp; Deletion"),
    ("core:security", "Security &amp; Responsible Disclosure"),
    ("core:review_guidelines", "Review Guidelines"),
)


@pytest.mark.django_db
@pytest.mark.parametrize(("route", "heading"), LEGAL_ROUTES)
def test_legal_center_documents_render_as_prelaunch_drafts(client, route, heading):
    response = client.get(reverse(route))
    content = response.content.decode()

    assert response.status_code == 200
    assert heading in content
    assert "Pre-launch policy draft" in content
    assert '<meta name="robots" content="noindex,nofollow">' in content


@pytest.mark.django_db
def test_legal_payment_copy_matches_current_ticket_fee_model(client):
    response = client.get(reverse("core:refunds"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "3.00% application fee" in content
    assert "not added as a separate attendee surcharge" in content
    assert "does not deduct an application fee from membership dues" in content


@pytest.mark.django_db
def test_site_footer_links_to_legal_center_and_payment_policy(client):
    response = client.get(reverse("core:home"))
    content = response.content.decode()

    assert reverse("core:legal") in content
    assert reverse("core:refunds") in content
