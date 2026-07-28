from django.urls import path

from . import views

app_name = "communications"

urlpatterns = [
    path("sites/<uuid:site_id>/campaigns/", views.campaign_list, name="campaign_list"),
    path(
        "sites/<uuid:site_id>/campaigns/new/",
        views.campaign_create,
        name="campaign_create",
    ),
    path(
        "sites/<uuid:site_id>/campaigns/<uuid:campaign_id>/edit/",
        views.campaign_edit,
        name="campaign_edit",
    ),
    path(
        "sites/<uuid:site_id>/campaigns/<uuid:campaign_id>/",
        views.campaign_preview_view,
        name="campaign_preview",
    ),
    path(
        "sites/<uuid:site_id>/campaigns/<uuid:campaign_id>/duplicate/",
        views.campaign_duplicate,
        name="campaign_duplicate",
    ),
    path(
        "communications/unsubscribe/<str:token>/",
        views.unsubscribe_view,
        name="unsubscribe",
    ),
    path(
        "communications/callbacks/<slug:provider>/",
        views.provider_callback,
        name="provider_callback",
    ),
]
