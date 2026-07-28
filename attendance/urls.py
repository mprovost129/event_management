from django.urls import path

from . import views

app_name = "attendance"

urlpatterns = [
    path(
        "sites/<uuid:site_id>/occurrences/<uuid:occurrence_id>/roster/",
        views.roster,
        name="roster",
    ),
    path(
        "sites/<uuid:site_id>/occurrences/<uuid:occurrence_id>/roster/<uuid:participant_id>/check-in/",
        views.toggle_check_in,
        name="toggle",
    ),
]
