from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("sites/<uuid:site_id>/events/", views.manage_events, name="manage"),
    path("sites/<uuid:site_id>/events/new/", views.event_create, name="create"),
    path(
        "sites/<uuid:site_id>/event-albums/",
        views.album_list,
        name="album_list",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/new/",
        views.album_create,
        name="album_create",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/<uuid:album_id>/",
        views.album_edit,
        name="album_edit",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/<uuid:album_id>/photos/",
        views.album_photo_upload,
        name="album_photo_upload",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/<uuid:album_id>/photos/reorder/",
        views.album_photo_reorder,
        name="album_photo_reorder",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/<uuid:album_id>/photos/<uuid:photo_id>/cover/",
        views.album_cover_set,
        name="album_cover_set",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/<uuid:album_id>/photos/<uuid:photo_id>/edit/",
        views.album_photo_edit,
        name="album_photo_edit",
    ),
    path(
        "sites/<uuid:site_id>/event-albums/<uuid:album_id>/photos/<uuid:photo_id>/delete/",
        views.album_photo_delete,
        name="album_photo_delete",
    ),
    path("sites/<uuid:site_id>/events/<uuid:event_id>/", views.event_edit, name="edit"),
    path(
        "sites/<uuid:site_id>/occurrences/<uuid:occurrence_id>/",
        views.occurrence_edit,
        name="occurrence_edit",
    ),
    path(
        "sites/<uuid:site_id>/occurrences/<uuid:occurrence_id>/invite/",
        views.invite_contacts,
        name="invite",
    ),
    path(
        "sites/<uuid:site_id>/occurrences/<uuid:occurrence_id>/responses/new/",
        views.manager_response,
        name="manager_response",
    ),
    path(
        "sites/<uuid:site_id>/events/<uuid:event_id>/cancel/",
        views.cancel_event,
        name="cancel",
    ),
    path("events/", views.calendar, name="calendar"),
    path("events/<slug:slug>/image/", views.public_event_image, name="event_image"),
    path("events/<slug:slug>/", views.event_detail, name="detail"),
    path(
        "events/<slug:slug>/<uuid:occurrence_id>/",
        views.occurrence_detail,
        name="occurrence_detail",
    ),
    path(
        "events/<slug:slug>/<uuid:occurrence_id>/respond/",
        views.public_response,
        name="public_response",
    ),
    path(
        "events/<slug:slug>/<uuid:occurrence_id>/respond/manage/<str:token>/",
        views.public_response_manage,
        name="public_response_manage",
    ),
    path(
        "invitations/<str:token>/",
        views.invitation_response,
        name="invitation_response",
    ),
    path("photos/", views.photo_album_list, name="photo_album_list"),
    path(
        "photos/<slug:slug>/",
        views.photo_album_detail,
        name="photo_album_detail",
    ),
]
