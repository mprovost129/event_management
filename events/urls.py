from django.urls import path

from . import views

app_name = "events"

urlpatterns = [
    path("sites/<uuid:site_id>/events/", views.manage_events, name="manage"),
    path("sites/<uuid:site_id>/events/new/", views.event_create, name="create"),
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
        "invitations/<str:token>/",
        views.invitation_response,
        name="invitation_response",
    ),
]
