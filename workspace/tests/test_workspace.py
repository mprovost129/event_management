from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from contacts.models import Contact
from sites.models import SiteRole
from sites.services import create_subscriber_site
from users.models import User
from workspace.ai_services import generate_content
from workspace.forms import DocumentForm, VolunteerProfileForm
from workspace.models import (
    Activity,
    AIContentDraft,
    AutomationRule,
    AutomationRun,
    Document,
    IntakeForm,
    IntakeSubmission,
    Sponsor,
    Sponsorship,
    VolunteerProfile,
    WorkTask,
)
from workspace.reporting import organization_insights


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


def add_manager(site, email):
    manager = User.objects.create_user(
        email=email,
        password="Strong-Test-Pass-2026!",
        email_verified_at=timezone.now(),
    )
    SiteRole.objects.create(
        site=site,
        user=manager,
        role=SiteRole.Role.SITE_MANAGER,
    )
    return manager


@pytest.mark.django_db
def test_workspace_routes_require_a_site_role_and_scope_objects(client):
    first_site, first_owner = create_site("first-group", "first@example.com")
    second_site, _ = create_site("second-group", "second@example.com")
    outsider = User.objects.create_user(
        email="outsider@example.com", password="Strong-Test-Pass-2026!"
    )
    foreign_task = WorkTask.objects.create(site=second_site, title="Foreign task")

    client.force_login(outsider)
    assert (
        client.get(reverse("workspace:task_list", args=(first_site.id,))).status_code
        == 403
    )

    client.force_login(first_owner)
    assert (
        client.get(reverse("workspace:task_list", args=(first_site.id,))).status_code
        == 200
    )
    assert (
        client.get(
            reverse("workspace:task_detail", args=(first_site.id, foreign_task.id))
        ).status_code
        == 404
    )


@pytest.mark.django_db
def test_workspace_task_list_is_paginated(client):
    site, owner = create_site("first-group", "first@example.com")
    WorkTask.objects.bulk_create(
        [WorkTask(site=site, title=f"Task {number:02d}") for number in range(26)]
    )
    client.force_login(owner)

    first_page = client.get(reverse("workspace:task_list", args=(site.id,)))
    second_page = client.get(
        reverse("workspace:task_list", args=(site.id,)), {"page": 2}
    )

    assert first_page.status_code == second_page.status_code == 200
    assert len(first_page.context["tasks"]) == 25
    assert len(second_page.context["tasks"]) == 1
    assert "Page 1 of 2" in first_page.content.decode()


@pytest.mark.django_db
def test_workspace_forms_reject_cross_tenant_relationships():
    first_site, _ = create_site("first-group", "first@example.com")
    second_site, _ = create_site("second-group", "second@example.com")
    foreign_contact = Contact.objects.create(
        site=second_site,
        first_name="Foreign",
        last_name="Contact",
        email="foreign@example.com",
    )

    form = VolunteerProfileForm(
        {
            "contact": foreign_contact.id,
            "status": VolunteerProfile.Status.ACTIVE,
            "skills": "Setup",
        },
        site=first_site,
    )

    assert not form.is_valid()
    assert "contact" in form.errors


@pytest.mark.django_db
def test_document_upload_validation_and_admin_visibility(settings):
    site, _ = create_site("first-group", "first@example.com")
    executable = SimpleUploadedFile("payload.exe", b"not executable")
    invalid_type = DocumentForm(
        {
            "title": "Payload",
            "category": Document.Category.OTHER,
            "visibility": Document.Visibility.STAFF,
        },
        {"file": executable},
        site=site,
    )
    assert not invalid_type.is_valid()
    assert "file" in invalid_type.errors

    settings.DOCUMENT_UPLOAD_MAX_BYTES = 3
    oversized = DocumentForm(
        {
            "title": "Oversized",
            "category": Document.Category.OTHER,
            "visibility": Document.Visibility.STAFF,
        },
        {"file": SimpleUploadedFile("notes.txt", b"four")},
        site=site,
    )
    assert not oversized.is_valid()
    assert "smaller" in oversized.errors["file"][0]

    manager_form = DocumentForm(
        {
            "title": "Admin only",
            "category": Document.Category.OTHER,
            "visibility": Document.Visibility.ADMIN,
        },
        {"file": SimpleUploadedFile("notes.txt", b"ok")},
        site=site,
        can_manage_admin_documents=False,
    )
    assert not manager_form.is_valid()
    assert "visibility" in manager_form.errors


@pytest.mark.django_db
def test_document_download_enforces_role_and_tenant_boundaries(client):
    first_site, first_owner = create_site("first-group", "first@example.com")
    manager = add_manager(first_site, "manager@example.com")
    second_site, _ = create_site("second-group", "second@example.com")
    admin_document = Document(
        site=first_site,
        title="Board notes",
        visibility=Document.Visibility.ADMIN,
    )
    admin_document.file.save("board.txt", ContentFile(b"owner only"), save=True)
    foreign_document = Document(site=second_site, title="Foreign")
    foreign_document.file.save("foreign.txt", ContentFile(b"foreign"), save=True)

    client.force_login(manager)
    denied = client.get(
        reverse("workspace:document_download", args=(first_site.id, admin_document.id))
    )
    assert denied.status_code == 403

    client.force_login(first_owner)
    allowed = client.get(
        reverse("workspace:document_download", args=(first_site.id, admin_document.id))
    )
    cross_tenant = client.get(
        reverse(
            "workspace:document_download", args=(first_site.id, foreign_document.id)
        )
    )
    assert allowed.status_code == 200
    assert b"".join(allowed.streaming_content) == b"owner only"
    assert cross_tenant.status_code == 404


@pytest.mark.django_db
def test_contact_profile_does_not_leak_admin_document_metadata(client):
    site, _ = create_site("first-group", "first@example.com")
    manager = add_manager(site, "manager@example.com")
    contact = Contact.objects.create(site=site, first_name="Alex", last_name="Rivera")
    document = Document(
        site=site,
        contact=contact,
        title="Confidential board notes",
        visibility=Document.Visibility.ADMIN,
    )
    document.file.save("board.txt", ContentFile(b"owner only"), save=True)
    client.force_login(manager)

    response = client.get(reverse("contacts:detail", args=(site.id, contact.id)))

    assert response.status_code == 200
    assert "Confidential board notes" not in response.content.decode()


@pytest.mark.django_db
def test_form_submission_creates_contact_and_runs_tenant_automation(client):
    site, owner = create_site("first-group", "first@example.com")
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    intake_form = IntakeForm.objects.create(
        site=site,
        title="Volunteer interest",
        slug="volunteer-interest",
        kind=IntakeForm.Kind.VOLUNTEER,
        fields=[
            {
                "key": "first_name",
                "label": "First name",
                "type": "text",
                "required": True,
            },
            {
                "key": "last_name",
                "label": "Last name",
                "type": "text",
                "required": True,
            },
            {"key": "email", "label": "Email", "type": "email", "required": True},
        ],
    )
    AutomationRule.objects.create(
        site=site,
        name="Follow up",
        trigger=AutomationRule.Trigger.FORM_SUBMITTED,
        trigger_config={"form_id": str(intake_form.id)},
        action=AutomationRule.Action.CREATE_TASK,
        action_config={"title": "Follow up with {{ submitter_name }}"},
        created_by=owner,
    )

    response = client.post(
        reverse("workspace:intake_public", args=(intake_form.id, intake_form.slug)),
        {"first_name": "Alex", "last_name": "Rivera", "email": "alex@example.com"},
    )

    submission = IntakeSubmission.objects.get(intake_form=intake_form)
    assert response.status_code == 200
    assert submission.contact.email == "alex@example.com"
    assert WorkTask.objects.filter(
        site=site, title="Follow up with Alex Rivera"
    ).exists()
    assert AutomationRun.objects.filter(
        site=site, status=AutomationRun.Status.SUCCEEDED
    ).exists()
    assert Activity.objects.filter(site=site, kind="form").exists()


@pytest.mark.django_db
def test_relationship_operations_and_insights_are_tenant_scoped():
    first_site, _ = create_site("first-group", "first@example.com")
    second_site, _ = create_site("second-group", "second@example.com")
    contact = Contact.objects.create(
        site=first_site, first_name="Alex", last_name="Rivera"
    )
    volunteer = VolunteerProfile.objects.create(site=first_site, contact=contact)
    sponsor = Sponsor.objects.create(
        site=first_site, name="Local Bank", status=Sponsor.Status.ACTIVE
    )
    Sponsorship.objects.create(
        site=first_site,
        sponsor=sponsor,
        status=Sponsorship.Status.PAID,
        amount_cents=25000,
    )
    WorkTask.objects.create(site=first_site, title="Current task")
    WorkTask.objects.create(site=second_site, title="Foreign task")

    insights = organization_insights(first_site)

    assert volunteer.site == first_site
    assert insights["tasks"]["open"] == 1
    assert insights["volunteers"]["active"] == 1
    assert insights["sponsors"]["paid_display"] == 250


@pytest.mark.django_db
def test_insights_export_uses_display_name_and_neutralizes_formulas(client):
    site, owner = create_site("first-group", "first@example.com")
    site.display_name = '=HYPERLINK("https://example.invalid")'
    site.save(update_fields=("display_name", "updated_at"))
    client.force_login(owner)

    response = client.get(reverse("workspace:insights_export", args=(site.id,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "'=HYPERLINK" in content
    assert "Gather HQs organization report" in content


@pytest.mark.django_db
def test_ai_content_fallback_is_saved_as_a_human_review_draft(settings):
    site, owner = create_site("first-group", "first@example.com")
    settings.OPENAI_API_KEY = ""
    draft = AIContentDraft.objects.create(
        site=site,
        created_by=owner,
        content_type=AIContentDraft.ContentType.EVENT_DESCRIPTION,
        title="Community picnic",
        instructions="Write a friendly invitation.",
        context=f"Starts in {timedelta(days=7).days} days.",
    )

    output, provider, model = generate_content(draft)

    assert provider == "template"
    assert model == "local-template"
    assert "Review this draft" in output
