from io import BytesIO
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from contacts.models import ConsentRecord, ConsentStatus, Contact
from content.forms import BlogPostForm
from content.images import prepare_image
from content.sanitization import sanitize_rich_text
from content.models import (
    BlogPost,
    PageSection,
    PageSectionImage,
    PublishingStatus,
    SitePage,
)
from content.services import public_page
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
def test_publishing_a_scheduled_blog_post_clears_the_stale_publish_at(client):
    owner, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    future = timezone.now() + timezone.timedelta(days=7)
    post = BlogPost.objects.create(
        site=site,
        title="Dance night update",
        slug="dance-night-update",
        excerpt="New details",
        body="Bring your dancing shoes.",
        status=PublishingStatus.SCHEDULED,
        publish_at=future,
    )
    client.force_login(owner)

    response = client.post(
        reverse("content:blog_edit", args=(site.id, post.id)),
        {
            "title": post.title,
            "slug": post.slug,
            "excerpt": post.excerpt,
            "body": post.body,
            "author_display_name": "",
            "status": PublishingStatus.PUBLISHED,
            "publish_at": future.strftime("%Y-%m-%dT%H:%M"),
            "meta_description": "",
        },
    )

    assert response.status_code == 302
    post.refresh_from_db()
    assert post.status == PublishingStatus.PUBLISHED
    assert post.publish_at is None

    public_page = client.get(
        reverse("content:blog_index"), headers={"host": f"{site.slug}.localhost"}
    )
    assert "Dance night update" in public_page.content.decode()


@pytest.mark.django_db
def test_publishing_a_scheduled_site_page_clears_the_stale_publish_at(client):
    owner, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    future = timezone.now() + timezone.timedelta(days=7)
    page = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    page.status = PublishingStatus.SCHEDULED
    page.publish_at = future
    page.save(update_fields=("status", "publish_at", "updated_at"))
    client.force_login(owner)

    response = client.post(
        reverse("content:page_edit", args=(site.id, SitePage.PageType.ABOUT)),
        {
            "title": page.title,
            "navigation_label": page.navigation_label,
            "body": "Our group has been dancing since 2019.",
            "status": PublishingStatus.PUBLISHED,
            "publish_at": future.strftime("%Y-%m-%dT%H:%M"),
            "meta_title": "",
            "meta_description": "",
        },
    )

    assert response.status_code == 302
    page.refresh_from_db()
    assert page.status == PublishingStatus.PUBLISHED
    assert page.publish_at is None
    assert page.is_public is True


@pytest.mark.django_db
def test_public_page_hides_a_published_page_with_a_stray_future_publish_at():
    _, site = create_site()
    future = timezone.now() + timezone.timedelta(days=7)
    page = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    # A leftover future publish_at from before this bug was fixed - the
    # query must not treat "published" as an unconditional override.
    page.status = PublishingStatus.PUBLISHED
    page.publish_at = future
    page.save(update_fields=("status", "publish_at", "updated_at"))

    assert public_page(site, SitePage.PageType.ABOUT) is None
    assert page.is_public is False

    page.publish_at = timezone.now() - timezone.timedelta(minutes=1)
    page.save(update_fields=("publish_at", "updated_at"))
    assert public_page(site, SitePage.PageType.ABOUT) == page
    assert page.is_public is True


@pytest.mark.django_db
def test_double_submitted_blog_slug_shows_a_friendly_error_not_a_500(client):
    owner, site = create_site()
    BlogPost.objects.create(
        site=site,
        title="Existing post",
        slug="dance-night-update",
        body="Already here.",
        status=PublishingStatus.PUBLISHED,
    )
    client.force_login(owner)

    # clean_slug()'s uniqueness check and the insert aren't atomic - simulate
    # the narrow window where a second, identically slugged submission
    # already passed validation before this one commits.
    with mock.patch.object(
        BlogPostForm, "clean_slug", lambda self: self.cleaned_data["slug"].lower()
    ):
        response = client.post(
            reverse("content:blog_create", args=(site.id,)),
            {
                "title": "Dance night update",
                "slug": "dance-night-update",
                "excerpt": "New details",
                "body": "Bring your dancing shoes.",
                "author_display_name": "",
                "status": PublishingStatus.PUBLISHED,
                "publish_at": "",
                "meta_description": "",
            },
        )

    assert response.status_code == 200
    assert "That blog URL is already in use" in response.content.decode()
    assert BlogPost.objects.filter(site=site, slug="dance-night-update").count() == 1


@pytest.mark.django_db
def test_public_brand_asset_provides_stable_email_image_url(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    site.theme.hero_image.name = "site-heroes/dance.jpg"
    site.theme.save(update_fields=("hero_image", "updated_at"))

    response = client.get(
        reverse("content:public_brand_asset", kwargs={"asset": "hero"}),
        headers={"host": "boot-scooters.localhost"},
    )
    missing = client.get(
        reverse("content:public_brand_asset", kwargs={"asset": "logo"}),
        headers={"host": "boot-scooters.localhost"},
    )

    assert response.status_code == 302
    assert response.url.endswith("/media/site-heroes/dance.jpg")
    assert response.headers["Cache-Control"] == "public, max-age=300"
    assert missing.status_code == 404


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


@pytest.mark.django_db
def test_published_page_renders_legacy_body_section(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    about = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    about.body = "About our group"
    about.status = PublishingStatus.PUBLISHED
    about.publish_at = timezone.now() - timezone.timedelta(minutes=1)
    about.save(update_fields=("body", "status", "publish_at", "updated_at"))

    PageSection.objects.create(
        site=site,
        page=about,
        section_type=PageSection.SectionType.CONTENT,
        position=1,
        is_enabled=True,
        is_legacy_body=True,
        heading="About",
        rich_text=about.body,
    )

    response = client.get(
        reverse("content:about"), headers={"host": "boot-scooters.localhost"}
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "About our group" in content


@pytest.mark.django_db
def test_custom_sections_override_legacy_body_rendering(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    about = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    about.body = "Legacy content should be hidden once custom sections exist"
    about.status = PublishingStatus.PUBLISHED
    about.publish_at = timezone.now() - timezone.timedelta(minutes=1)
    about.save(update_fields=("body", "status", "publish_at", "updated_at"))

    PageSection.objects.create(
        site=site,
        page=about,
        section_type=PageSection.SectionType.CONTENT,
        position=1,
        is_enabled=True,
        is_legacy_body=True,
        heading="Legacy",
        rich_text=about.body,
    )
    PageSection.objects.create(
        site=site,
        page=about,
        section_type=PageSection.SectionType.HERO,
        position=2,
        is_enabled=True,
        heading="Meet Boot Scooters",
        subheading="Weekly lessons and social dances",
    )

    response = client.get(
        reverse("content:about"), headers={"host": "boot-scooters.localhost"}
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Meet Boot Scooters" in content
    assert "Legacy content should be hidden" not in content


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


def section_image_upload(name="section.jpg", *, width=1200, height=900):
    source = BytesIO()
    Image.new("RGB", (width, height), color="navy").save(source, format="JPEG")
    return SimpleUploadedFile(name, source.getvalue(), content_type="image/jpeg")


@pytest.mark.django_db
def test_website_hub_guides_owner_through_three_setup_steps(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.get(reverse("content:manage", args=(site.id,)))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Website setup" in content
    assert "0 of 3 complete" in content
    assert "boot-scooters.localhost" in content
    assert "Write your homepage" in content


@pytest.mark.django_db
def test_owner_can_design_and_publish_site_from_guided_builder(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.post(
        reverse("content:presentation", args=(site.id,)),
        {
            "display_name": "Boot Scooters Dance Club",
            "template_key": "social",
            "is_published": "on",
            "hero_heading": "Dance with us",
            "hero_text": "Friendly lessons and social dances every week.",
            "primary_color": "#234567",
            "secondary_color": "#567890",
            "typography_key": "rounded",
        },
    )

    site.refresh_from_db()
    site.theme.refresh_from_db()
    assert response.status_code == 302
    assert response.url == reverse("content:manage", args=(site.id,))
    assert site.display_name == "Boot Scooters Dance Club"
    assert site.template_key == "social"
    assert site.is_published is True
    assert site.theme.hero_heading == "Dance with us"
    assert site.theme.primary_color == "#234567"


@pytest.mark.django_db
def test_design_builder_includes_live_preview_controls(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.get(reverse("content:presentation", args=(site.id,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Homepage preview" in content
    assert "data-site-builder-form" in content
    assert 'type="color"' in content
    assert "Your content moves with you if you switch later" in content


@pytest.mark.django_db
def test_blog_editor_explains_publish_then_newsletter_workflow(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.get(reverse("content:blog_create", args=(site.id,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Share an update with your group" in content
    assert "data-blog-editor" in content
    assert "Write once, share twice" in content
    assert "/blog/" in content


@pytest.mark.django_db
def test_page_editor_section_actions_add_move_and_delete(client):
    owner, site = create_site()
    client.force_login(owner)

    edit_url = reverse("content:page_edit", args=(site.id, SitePage.PageType.ABOUT))

    add_hero = client.post(
        edit_url,
        {"section_action": "add", "section_type": PageSection.SectionType.HERO},
    )
    add_content = client.post(
        edit_url,
        {"section_action": "add", "section_type": PageSection.SectionType.CONTENT},
    )

    sections = list(PageSection.objects.for_site(site).order_by("position"))
    assert add_hero.status_code == 302
    assert add_content.status_code == 302
    assert [section.section_type for section in sections] == [
        PageSection.SectionType.HERO,
        PageSection.SectionType.CONTENT,
    ]

    move_up = client.post(
        edit_url,
        {
            "section_action": "move",
            "section_id": str(sections[1].id),
            "direction": "up",
        },
    )
    reordered = list(PageSection.objects.for_site(site).order_by("position"))
    assert move_up.status_code == 302
    assert [section.section_type for section in reordered] == [
        PageSection.SectionType.CONTENT,
        PageSection.SectionType.HERO,
    ]

    delete = client.post(
        edit_url,
        {
            "section_action": "delete",
            "section_id": str(reordered[1].id),
        },
    )
    remaining = list(PageSection.objects.for_site(site).order_by("position"))
    assert delete.status_code == 302
    assert len(remaining) == 1
    assert remaining[0].position == 1


@pytest.mark.django_db
def test_strip_section_image_requires_alt_text_and_limits_to_six(client):
    owner, site = create_site()
    client.force_login(owner)
    page = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    strip = PageSection.objects.create(
        site=site,
        page=page,
        section_type=PageSection.SectionType.STRIP,
        position=1,
    )
    edit_url = reverse("content:page_edit", args=(site.id, SitePage.PageType.ABOUT))

    missing_alt = client.post(
        edit_url,
        {
            "section_action": "add_strip_image",
            "section_id": str(strip.id),
            "alt_text": "",
            "image": section_image_upload("one.jpg"),
        },
        follow=True,
    )
    assert missing_alt.status_code == 200
    assert "Alt text is required for each strip image" in missing_alt.content.decode()
    assert strip.images.count() == 0

    for index in range(6):
        response = client.post(
            edit_url,
            {
                "section_action": "add_strip_image",
                "section_id": str(strip.id),
                "alt_text": f"Logo {index + 1}",
                "image": section_image_upload(f"logo-{index + 1}.jpg"),
            },
        )
        assert response.status_code == 302
    assert strip.images.count() == 6
    assert PageSectionImage.objects.for_site(site).filter(section=strip).count() == 6

    over_limit = client.post(
        edit_url,
        {
            "section_action": "add_strip_image",
            "section_id": str(strip.id),
            "alt_text": "Logo 7",
            "image": section_image_upload("logo-7.jpg"),
        },
        follow=True,
    )
    assert over_limit.status_code == 200
    assert "Strip sections can include up to 6 images" in over_limit.content.decode()
    assert strip.images.count() == 6


def test_sanitize_rich_text_keeps_safe_markup_and_strips_unsafe_html():
    source = (
        "<h2>Welcome</h2><p><strong>Bold</strong> and <em>emphasis</em>.</p>"
        "<script>alert(1)</script>"
        '<a href="javascript:alert(1)" onclick="evil()">Bad link</a>'
        '<a href="https://example.com">Good link</a>'
    )

    result = sanitize_rich_text(source)

    assert "<h2>Welcome</h2>" in result
    assert "<strong>Bold</strong>" in result
    assert "<em>emphasis</em>" in result
    assert "<script" not in result
    assert "onclick=" not in result
    assert "javascript:" not in result
    assert 'href="https://example.com"' in result


@pytest.mark.django_db
def test_public_content_section_renders_sanitized_rich_text(client):
    _, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    about = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    about.status = PublishingStatus.PUBLISHED
    about.publish_at = timezone.now() - timezone.timedelta(minutes=1)
    about.save(update_fields=("status", "publish_at", "updated_at"))

    PageSection.objects.create(
        site=site,
        page=about,
        section_type=PageSection.SectionType.CONTENT,
        is_enabled=True,
        position=1,
        heading="About",
        rich_text=(
            "<p>Visit <a href='https://example.com'>our link</a>.</p>"
            "<img src=x onerror=alert(1)>"
            "<script>alert(2)</script>"
        ),
    )

    response = client.get(
        reverse("content:about"), headers={"host": "boot-scooters.localhost"}
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "our link" in content
    assert "href=\"https://example.com\"" in content
    assert "alert(2)" not in content
    assert "onerror=" not in content


@pytest.mark.django_db
def test_page_edit_preserves_legacy_body_when_custom_sections_exist(client):
    owner, site = create_site()
    client.force_login(owner)
    page = SitePage.objects.get(site=site, page_type=SitePage.PageType.ABOUT)
    page.body = "Legacy body should remain unchanged."
    page.status = PublishingStatus.DRAFT
    page.save(update_fields=("body", "status", "updated_at"))
    PageSection.objects.create(
        site=site,
        page=page,
        section_type=PageSection.SectionType.HERO,
        position=1,
        heading="New section content",
        is_enabled=True,
    )

    edit_url = reverse("content:page_edit", args=(site.id, SitePage.PageType.ABOUT))
    get_response = client.get(edit_url)
    assert get_response.status_code == 200
    assert "legacy body field is read-only fallback" in get_response.content.decode().lower()

    post_response = client.post(
        edit_url,
        {
            "title": "About",
            "navigation_label": "About",
            "status": PublishingStatus.PUBLISHED,
            "publish_at": "",
            "meta_title": "About Boot Scooters",
            "meta_description": "Learn more about Boot Scooters.",
        },
    )

    page.refresh_from_db()
    assert post_response.status_code == 302
    assert page.body == "Legacy body should remain unchanged."
    assert page.status == PublishingStatus.PUBLISHED
