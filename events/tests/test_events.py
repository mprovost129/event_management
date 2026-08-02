from datetime import datetime, timedelta
from io import BytesIO
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from contacts.models import Contact
from events.forms import EventAlbumCreateForm, EventForm
from events.models import Event, EventAlbum, EventOccurrence, EventPhoto
from events.services import (
    create_event_series,
    occurrence_starts,
    update_occurrences_from,
)
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


def create_series(site, owner, *, visibility=Event.Visibility.PUBLIC, slug="lessons"):
    first_start = datetime(2026, 8, 3, 18, 0, tzinfo=ZoneInfo(site.timezone))
    return create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": f"{visibility.title()} lessons",
            "slug": slug,
            "description": "Weekly country line dancing.",
            "host_name": "Pat",
            "visibility": visibility,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.WEEKLY,
            "recurrence_interval": 1,
            "recurrence_until": first_start.date() + timedelta(weeks=2),
        },
        first_start=first_start,
        first_end=first_start + timedelta(hours=2),
        venue_name="Town Hall",
        capacity=40,
    )


def image_upload(name="event.jpg", *, width=1800, height=1200):
    source = BytesIO()
    Image.new("RGB", (width, height), color="navy").save(source, format="JPEG")
    return SimpleUploadedFile(name, source.getvalue(), content_type="image/jpeg")


@pytest.mark.django_db
def test_event_manager_filters_without_per_occurrence_metric_queries(client):
    owner, site = create_site()
    event = Event.objects.create(
        site=site,
        created_by=owner,
        title="Welcome dance",
        slug="welcome-dance",
        status=Event.Status.PUBLISHED,
    )
    Event.objects.create(
        site=site,
        created_by=owner,
        title="Archived dance",
        slug="archived-dance",
        status=Event.Status.ARCHIVED,
    )
    starts_at = timezone.now() + timedelta(days=1)
    EventOccurrence.objects.bulk_create(
        [
            EventOccurrence(
                site=site,
                event=event,
                starts_at=starts_at + timedelta(days=number),
                ends_at=starts_at + timedelta(days=number, hours=2),
                timezone=site.timezone,
                capacity=50,
            )
            for number in range(10)
        ]
    )
    client.force_login(owner)

    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("events:manage", args=(site.id,)))
    filtered = client.get(
        reverse("events:manage", args=(site.id,)),
        {"q": "Welcome", "status": "published"},
    )

    assert response.status_code == filtered.status_code == 200
    assert len(queries) < 20
    assert "Welcome dance" in filtered.content.decode()
    assert "Archived dance" not in filtered.content.decode()
    assert 'data-confirm="Cancel this event and notify affected participants?"' in (
        filtered.content.decode()
    )


@pytest.mark.django_db
def test_weekly_series_materializes_occurrences_in_site_timezone():
    owner, site = create_site()
    event = create_series(site, owner)

    occurrences = list(event.occurrences.all())
    assert len(occurrences) == 3
    assert all(item.timezone == "America/New_York" for item in occurrences)
    assert occurrences[1].starts_at - occurrences[0].starts_at == timedelta(weeks=1)


def test_monthly_recurrence_keeps_the_original_day_after_a_short_month():
    first = datetime(2027, 1, 31, 18, 0, tzinfo=ZoneInfo("America/New_York"))

    starts = list(
        occurrence_starts(
            first,
            Event.Recurrence.MONTHLY,
            1,
            datetime(2027, 3, 31).date(),
        )
    )

    assert [item.day for item in starts] == [31, 28, 31]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("scope", "shifted_indexes"),
    (("one", {1}), ("future", {1, 2}), ("all", {0, 1, 2})),
)
def test_occurrence_edit_scopes_change_the_expected_dates(scope, shifted_indexes):
    owner, site = create_site()
    event = create_series(site, owner)
    before = list(event.occurrences.values_list("starts_at", flat=True))
    target = event.occurrences.all()[1]

    update_occurrences_from(
        occurrence=target,
        scope=scope,
        values={
            "starts_at": target.starts_at + timedelta(hours=1),
            "ends_at": target.ends_at + timedelta(hours=1),
            "venue_name": "New Hall",
            "venue_address": "100 Main Street",
            "capacity": 50,
            "status": EventOccurrence.Status.SCHEDULED,
        },
    )

    after = list(event.occurrences.values_list("starts_at", flat=True))
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        expected = old + timedelta(hours=1) if index in shifted_indexes else old
        assert new == expected


@pytest.mark.django_db
def test_calendar_lists_public_events_but_direct_unlisted_links_work(client):
    owner, site = create_site()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    public = create_series(site, owner, slug="public-lessons")
    unlisted = create_series(
        site, owner, visibility=Event.Visibility.UNLISTED, slug="unlisted-lessons"
    )
    invite_only = create_series(
        site, owner, visibility=Event.Visibility.INVITE_ONLY, slug="private-lessons"
    )
    host = {"host": "boot-scooters.localhost"}

    calendar_response = client.get(reverse("events:calendar"), headers=host)
    unlisted_response = client.get(
        reverse("events:detail", kwargs={"slug": unlisted.slug}), headers=host
    )
    private_response = client.get(
        reverse("events:detail", kwargs={"slug": invite_only.slug}), headers=host
    )

    calendar_content = calendar_response.content.decode()
    assert public.title in calendar_content
    assert unlisted.title not in calendar_content
    assert invite_only.title not in calendar_content
    assert unlisted_response.status_code == 200
    assert private_response.status_code == 404


@pytest.mark.django_db
def test_event_editor_guides_owner_through_access_and_recurrence(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.get(reverse("events:create", args=(site.id,)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "data-event-editor" in content
    assert "Who can attend?" in content
    assert "Does it repeat?" in content
    assert "Create event and continue" in content
    assert response.context["form"].initial["host_name"] == site.display_name


@pytest.mark.django_db
def test_new_event_redirects_to_highlighted_next_actions(client):
    owner, site = create_site()
    client.force_login(owner)

    response = client.post(
        reverse("events:create", args=(site.id,)),
        {
            "title": "Friday Night Line Dance",
            "slug": "friday-night-line-dance",
            "description": "A friendly social dance for all levels.",
            "host_name": site.display_name,
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": "",
            "max_guests": 2,
            "start_date": "2026-09-18",
            "start_time": "19:00",
            "end_date": "2026-09-18",
            "end_time": "21:00",
            "venue_name": "Town Hall",
            "venue_address": "100 Main Street",
            "capacity": 60,
        },
    )

    event = Event.objects.get(slug="friday-night-line-dance")
    assert response.status_code == 302
    assert response.url.endswith(f"?created={event.id}")

    followup = client.get(response.url)
    content = followup.content.decode()
    assert "What would you like to do next?" in content
    assert "Invite contacts" in content
    assert "Add tickets" in content
    assert "Friday Night Line Dance" in content


@pytest.mark.django_db
def test_double_submitted_event_slug_shows_a_friendly_error_not_a_500(client):
    owner, site = create_site()
    Event.objects.create(
        site=site,
        created_by=owner,
        title="Existing event",
        slug="friday-night-line-dance",
        status=Event.Status.PUBLISHED,
    )
    client.force_login(owner)

    # clean_slug()'s uniqueness check and create_event_series()'s insert
    # aren't atomic - simulate the narrow window where a second, identically
    # slugged submission already passed validation before this one commits.
    with mock.patch.object(
        EventForm, "clean_slug", lambda self: self.cleaned_data["slug"].lower()
    ):
        response = client.post(
            reverse("events:create", args=(site.id,)),
            {
                "title": "Friday Night Line Dance",
                "slug": "friday-night-line-dance",
                "description": "A friendly social dance for all levels.",
                "host_name": site.display_name,
                "visibility": Event.Visibility.PUBLIC,
                "status": Event.Status.PUBLISHED,
                "recurrence": Event.Recurrence.NONE,
                "recurrence_interval": 1,
                "recurrence_until": "",
                "max_guests": 2,
                "start_date": "2026-09-18",
                "start_time": "19:00",
                "end_date": "2026-09-18",
                "end_time": "21:00",
                "venue_name": "Town Hall",
                "venue_address": "100 Main Street",
                "capacity": 60,
            },
        )

    assert response.status_code == 200
    assert "That event URL is already in use" in response.content.decode()
    assert Event.objects.filter(site=site, slug="friday-night-line-dance").count() == 1


@pytest.mark.django_db
def test_double_submitted_album_slug_shows_a_friendly_error_not_a_500(client):
    owner, site = create_site()
    past_start = timezone.now() - timedelta(days=2)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Summer social",
            "slug": "summer-social",
            "description": "A joyful night with friends.",
            "host_name": "Pat",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 2,
        },
        first_start=past_start,
        first_end=past_start + timedelta(hours=2),
        venue_name="Town Hall",
    )
    occurrence = event.occurrences.get()
    EventAlbum.objects.create(
        site=site,
        occurrence=occurrence,
        created_by=owner,
        title="Existing album",
        slug="summer-social-highlights",
    )
    client.force_login(owner)

    # clean_slug()'s uniqueness check and album.save() aren't atomic -
    # simulate the narrow window where a second, identically slugged
    # submission already passed validation before this one commits.
    with mock.patch.object(
        EventAlbumCreateForm,
        "clean_slug",
        lambda self: self.cleaned_data["slug"].lower(),
    ):
        response = client.post(
            reverse("events:album_create", args=(site.id,)),
            {
                "occurrence": str(occurrence.id),
                "title": "Summer Social Highlights",
                "slug": "summer-social-highlights",
                "description": "Favorite moments from the dance floor.",
            },
        )

    assert response.status_code == 200
    assert "That album URL is already in use" in response.content.decode()
    assert (
        EventAlbum.objects.filter(site=site, slug="summer-social-highlights").count()
        == 1
    )
    # The connection must still be usable after the rolled-back savepoint -
    # prove it with a real follow-up query rather than just the status code.
    assert client.get(reverse("events:manage", args=(site.id,))).status_code == 200


@pytest.mark.django_db
def test_owner_uploads_event_promotional_image_for_public_page_and_email_url(client):
    owner, site = create_site()
    event = create_series(site, owner)
    client.force_login(owner)

    response = client.post(
        reverse("events:edit", args=(site.id, event.id)),
        {
            "title": event.title,
            "slug": event.slug,
            "description": event.description,
            "featured_image": image_upload(),
            "host_name": event.host_name,
            "visibility": event.visibility,
            "status": event.status,
            "max_guests": event.max_guests,
        },
    )

    event.refresh_from_db()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    public_page = client.get(
        reverse("events:detail", kwargs={"slug": event.slug}),
        headers={"host": "boot-scooters.localhost"},
    )
    image_response = client.get(
        reverse("events:event_image", kwargs={"slug": event.slug}),
        headers={"host": "boot-scooters.localhost"},
    )

    assert response.status_code == 302
    assert event.featured_image.name.startswith("event-images/")
    assert "gh-public-event-image" in public_page.content.decode()
    assert image_response.status_code == 302
    assert image_response.headers["Cache-Control"] == "public, max-age=300"


@pytest.mark.django_db
def test_invite_only_event_image_is_not_publicly_fetchable(client):
    owner, site = create_site()
    event = create_series(site, owner, visibility=Event.Visibility.INVITE_ONLY)
    client.force_login(owner)
    client.post(
        reverse("events:edit", args=(site.id, event.id)),
        {
            "title": event.title,
            "slug": event.slug,
            "description": event.description,
            "featured_image": image_upload(),
            "host_name": event.host_name,
            "visibility": event.visibility,
            "status": event.status,
            "max_guests": event.max_guests,
        },
    )
    event.refresh_from_db()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    client.logout()

    detail_response = client.get(
        reverse("events:detail", kwargs={"slug": event.slug}),
        headers={"host": "boot-scooters.localhost"},
    )
    image_response = client.get(
        reverse("events:event_image", kwargs={"slug": event.slug}),
        headers={"host": "boot-scooters.localhost"},
    )

    assert event.featured_image
    assert detail_response.status_code == 404
    assert image_response.status_code == 404


@pytest.mark.django_db
def test_owner_builds_and_publishes_album_for_completed_event(client):
    owner, site = create_site()
    past_start = timezone.now() - timedelta(days=2)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Summer social",
            "slug": "summer-social",
            "description": "A joyful night with friends.",
            "host_name": "Pat",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 2,
        },
        first_start=past_start,
        first_end=past_start + timedelta(hours=2),
        venue_name="Town Hall",
    )
    occurrence = event.occurrences.get()
    client.force_login(owner)

    create_response = client.post(
        reverse("events:album_create", args=(site.id,)),
        {
            "occurrence": str(occurrence.id),
            "title": "Summer Social Highlights",
            "slug": "summer-social-highlights",
            "description": "Favorite moments from the dance floor.",
        },
    )
    album = EventAlbum.objects.get(site=site)
    early_publish = client.post(
        reverse("events:album_edit", args=(site.id, album.id)),
        {
            "title": album.title,
            "slug": album.slug,
            "description": album.description,
            "status": EventAlbum.Status.PUBLISHED,
        },
    )
    upload_response = client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {
            "images": image_upload("dance-floor.jpg"),
            "alt_text": "A group of dancers smiling under blue lights",
        },
    )
    photo = EventPhoto.objects.get(album=album)
    client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {
            "images": image_upload("group-photo.jpg"),
            "alt_text": "Six friends posing together near the stage",
        },
    )
    second_photo = EventPhoto.objects.exclude(pk=photo.id).get(album=album)
    cover_response = client.post(
        reverse(
            "events:album_cover_set",
            args=(site.id, album.id, second_photo.id),
        )
    )
    album.refresh_from_db()
    selected_cover_id = album.cover_photo_id
    photo_edit_response = client.post(
        reverse(
            "events:album_photo_edit",
            args=(site.id, album.id, photo.id),
        ),
        {
            "caption": "Opening dance with everyone together",
            "alt_text": "A large group dancing together under blue lights",
        },
    )
    publish_response = client.post(
        reverse("events:album_edit", args=(site.id, album.id)),
        {
            "title": album.title,
            "slug": album.slug,
            "description": album.description,
            "status": EventAlbum.Status.PUBLISHED,
        },
    )

    album.refresh_from_db()
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    public_list = client.get(
        reverse("events:photo_album_list"),
        headers={"host": "boot-scooters.localhost"},
    )
    public_detail = client.get(
        reverse("events:photo_album_detail", args=(album.slug,)),
        headers={"host": "boot-scooters.localhost"},
    )
    delete_response = client.post(
        reverse(
            "events:album_photo_delete",
            args=(site.id, album.id, second_photo.id),
        )
    )
    album.refresh_from_db()
    other_owner, other_site = create_site("other-group")
    client.force_login(other_owner)
    cross_tenant = client.get(
        reverse("events:album_edit", args=(other_site.id, album.id))
    )

    assert create_response.status_code == 302
    assert album.status == EventAlbum.Status.PUBLISHED
    assert early_publish.status_code == 200
    assert "Add at least one photo" in early_publish.content.decode()
    assert upload_response.status_code == 302
    assert publish_response.status_code == 302
    assert cover_response.status_code == 302
    assert photo_edit_response.status_code == 302
    assert selected_cover_id == second_photo.id
    assert delete_response.status_code == 302
    assert album.cover_photo_id == photo.id
    assert album.photos.count() == 1
    assert photo.image.name.startswith("event-albums/")
    assert "Summer Social Highlights" in public_list.content.decode()
    assert "Opening dance with everyone together" in public_detail.content.decode()
    assert "A large group dancing together" in public_detail.content.decode()
    assert cross_tenant.status_code == 404


@pytest.mark.django_db
def test_deleting_the_last_photo_reverts_a_published_album_to_draft(client):
    owner, site = create_site()
    past_start = timezone.now() - timedelta(days=2)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": "Summer social",
            "slug": "summer-social",
            "description": "A joyful night with friends.",
            "host_name": "Pat",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 2,
        },
        first_start=past_start,
        first_end=past_start + timedelta(hours=2),
        venue_name="Town Hall",
    )
    occurrence = event.occurrences.get()
    client.force_login(owner)
    client.post(
        reverse("events:album_create", args=(site.id,)),
        {
            "occurrence": str(occurrence.id),
            "title": "Summer Social Highlights",
            "slug": "summer-social-highlights",
            "description": "Favorite moments from the dance floor.",
        },
    )
    album = EventAlbum.objects.get(site=site)
    client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {
            "images": image_upload("dance-floor.jpg"),
            "alt_text": "A group of dancers smiling under blue lights",
        },
    )
    photo = EventPhoto.objects.get(album=album)
    client.post(
        reverse("events:album_edit", args=(site.id, album.id)),
        {
            "title": album.title,
            "slug": album.slug,
            "description": album.description,
            "status": EventAlbum.Status.PUBLISHED,
        },
    )
    album.refresh_from_db()
    assert album.status == EventAlbum.Status.PUBLISHED

    delete_response = client.post(
        reverse("events:album_photo_delete", args=(site.id, album.id, photo.id)),
        follow=True,
    )

    album.refresh_from_db()
    assert delete_response.status_code == 200
    assert "moved back to Draft" in delete_response.content.decode()
    assert album.status == EventAlbum.Status.DRAFT
    assert album.photos.count() == 0

    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    public_list = client.get(
        reverse("events:photo_album_list"),
        headers={"host": "boot-scooters.localhost"},
    )
    public_detail = client.get(
        reverse("events:photo_album_detail", args=(album.slug,)),
        headers={"host": "boot-scooters.localhost"},
    )
    assert "Summer Social Highlights" not in public_list.content.decode()
    assert public_detail.status_code == 404


@pytest.mark.django_db
def test_future_event_date_cannot_be_used_for_past_event_album(client):
    owner, site = create_site()
    event = create_series(site, owner)
    occurrence = event.occurrences.first()
    client.force_login(owner)

    page = client.get(reverse("events:album_create", args=(site.id,)))
    response = client.post(
        reverse("events:album_create", args=(site.id,)),
        {
            "occurrence": str(occurrence.id),
            "title": "Too early",
            "slug": "too-early",
            "description": "This event has not happened yet.",
        },
    )

    assert occurrence not in page.context["form"].fields["occurrence"].queryset
    assert response.status_code == 200
    assert not EventAlbum.objects.exists()


@pytest.mark.django_db
def test_invitation_picker_shows_contact_email_and_search_controls(client):
    owner, site = create_site()
    event = create_series(site, owner)
    occurrence = event.occurrences.first()
    Contact.objects.create(
        site=site,
        first_name="Pat",
        last_name="Dancer",
        email="pat@example.com",
    )
    client.force_login(owner)

    response = client.get(reverse("events:invite", args=(site.id, occurrence.id)))
    content = response.content.decode()

    assert response.status_code == 200
    assert "data-invite-picker" in content
    assert "Pat Dancer - pat@example.com" in content
    assert "Search by name or email" in content
    assert "Personal invitation links" in content


def create_past_album(owner, site, *, title="Summer social"):
    past_start = timezone.now() - timedelta(days=2)
    event = create_event_series(
        site=site,
        creator=owner,
        event_values={
            "title": title,
            "slug": "summer-social",
            "description": "A joyful night with friends.",
            "host_name": "Pat",
            "visibility": Event.Visibility.PUBLIC,
            "status": Event.Status.PUBLISHED,
            "recurrence": Event.Recurrence.NONE,
            "recurrence_interval": 1,
            "recurrence_until": None,
            "max_guests": 2,
        },
        first_start=past_start,
        first_end=past_start + timedelta(hours=2),
        venue_name="Town Hall",
    )
    occurrence = event.occurrences.get()
    return EventAlbum.objects.create(
        site=site,
        occurrence=occurrence,
        title="Summer Social Highlights",
        slug="summer-social-highlights",
        created_by=owner,
    )


@pytest.mark.django_db
def test_bulk_photo_upload_stores_thumbnails_and_default_alt_text(client):
    owner, site = create_site()
    album = create_past_album(owner, site)
    client.force_login(owner)

    response = client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {
            "images": [
                image_upload("one.jpg"),
                image_upload("two.jpg"),
                image_upload("three.jpg"),
            ]
        },
    )

    photos = list(EventPhoto.objects.filter(album=album).order_by("position"))
    album.refresh_from_db()

    assert response.status_code == 302
    assert len(photos) == 3
    # Every photo gets a smaller derivative for grid rendering.
    assert all(photo.thumbnail for photo in photos)
    assert all(photo.thumbnail.name != photo.image.name for photo in photos)
    assert all(photo.preview.name == photo.thumbnail.name for photo in photos)
    # Dimensions are stored so templates can reserve space before load.
    assert all(photo.image_width and photo.image_height for photo in photos)
    # Alt text nobody typed still describes the photo usefully.
    assert photos[0].alt_text.startswith("Photo from Summer social on ")
    assert [photo.position for photo in photos] == [1, 2, 3]
    assert album.cover_photo_id == photos[0].id


@pytest.mark.django_db
def test_bulk_upload_applies_supplied_alt_text_to_every_photo(client):
    owner, site = create_site()
    album = create_past_album(owner, site)
    client.force_login(owner)

    client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {
            "images": [image_upload("one.jpg"), image_upload("two.jpg")],
            "alt_text": "Dancers in a line under string lights",
        },
    )

    alt_texts = {photo.alt_text for photo in EventPhoto.objects.filter(album=album)}
    assert alt_texts == {"Dancers in a line under string lights"}


@pytest.mark.django_db
def test_oversized_pixel_count_is_rejected_before_encoding(client):
    owner, site = create_site()
    album = create_past_album(owner, site)
    client.force_login(owner)

    with mock.patch("content.images.MAX_IMAGE_PIXELS", 1000):
        response = client.post(
            reverse("events:album_photo_upload", args=(site.id, album.id)),
            {"images": image_upload("huge.jpg")},
        )

    assert response.status_code == 400
    assert "under 50 megapixels" in response.content.decode()
    assert not EventPhoto.objects.filter(album=album).exists()


@pytest.mark.django_db
def test_photo_reorder_persists_new_positions_and_rejects_foreign_ids(client):
    owner, site = create_site()
    album = create_past_album(owner, site)
    client.force_login(owner)
    client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {
            "images": [
                image_upload("a.jpg"),
                image_upload("b.jpg"),
                image_upload("c.jpg"),
            ]
        },
    )
    original = list(EventPhoto.objects.filter(album=album).order_by("position"))
    reversed_ids = [str(photo.id) for photo in reversed(original)]

    ok = client.post(
        reverse("events:album_photo_reorder", args=(site.id, album.id)),
        {"photo_ids": reversed_ids},
    )
    reordered = list(EventPhoto.objects.filter(album=album).order_by("position"))

    partial = client.post(
        reverse("events:album_photo_reorder", args=(site.id, album.id)),
        {"photo_ids": reversed_ids[:2]},
    )
    empty = client.post(
        reverse("events:album_photo_reorder", args=(site.id, album.id)),
        {},
    )

    assert ok.status_code == 200
    assert [photo.id for photo in reordered] == [
        photo.id for photo in reversed(original)
    ]
    # A partial or empty order is refused rather than silently applied.
    assert partial.status_code == 400
    assert empty.status_code == 400


@pytest.mark.django_db
def test_public_album_list_does_not_query_per_album(client):
    owner, site = create_site()
    client.force_login(owner)
    for index in range(3):
        album = create_past_album(owner, site, title=f"Social {index}")
        album.slug = f"social-{index}"
        album.save(update_fields=("slug",))
        album.occurrence.event.slug = f"social-event-{index}"
        album.occurrence.event.save(update_fields=("slug",))
        client.post(
            reverse("events:album_photo_upload", args=(site.id, album.id)),
            {"images": image_upload(f"{index}.jpg")},
        )
        client.post(
            reverse("events:album_edit", args=(site.id, album.id)),
            {
                "title": album.title,
                "slug": album.slug,
                "description": "",
                "status": EventAlbum.Status.PUBLISHED,
            },
        )
    site.is_published = True
    site.save(update_fields=("is_published", "updated_at"))
    client.logout()

    with CaptureQueriesContext(connection) as captured:
        response = client.get(
            reverse("events:photo_album_list"),
            headers={"host": "boot-scooters.localhost"},
        )

    assert response.status_code == 200
    # Cover lookups must come from the prefetch cache, not one query per album.
    assert len(captured) < 15


@pytest.mark.django_db
def test_photo_delete_removes_both_stored_derivatives(
    client, django_capture_on_commit_callbacks
):
    owner, site = create_site()
    album = create_past_album(owner, site)
    client.force_login(owner)
    client.post(
        reverse("events:album_photo_upload", args=(site.id, album.id)),
        {"images": image_upload("only.jpg")},
    )
    photo = EventPhoto.objects.get(album=album)
    storage = photo.image.storage
    image_name = photo.image.name
    thumbnail_name = photo.thumbnail.name

    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("events:album_photo_delete", args=(site.id, album.id, photo.id))
        )

    # Both derivatives are cleaned up so deleted photos do not bill storage
    # forever.
    assert not storage.exists(image_name)
    assert not storage.exists(thumbnail_name)
