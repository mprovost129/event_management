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
    path("events/", views.calendar, name="calendar"),
    path("events/<slug:slug>/", views.event_detail, name="detail"),
    path(
        "events/<slug:slug>/<uuid:occurrence_id>/",
        views.occurrence_detail,
        name="occurrence_detail",
    ),
]
