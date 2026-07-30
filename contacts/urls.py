from django.urls import path

from . import views

app_name = "contacts"

urlpatterns = [
    path("sites/<uuid:site_id>/contacts/", views.contact_list, name="list"),
    path("sites/<uuid:site_id>/contacts/new/", views.contact_create, name="create"),
    path(
        "sites/<uuid:site_id>/contacts/<uuid:contact_id>/",
        views.contact_edit,
        name="edit",
    ),
    path(
        "sites/<uuid:site_id>/contacts/<uuid:contact_id>/archive/",
        views.contact_archive,
        name="archive",
    ),
]
