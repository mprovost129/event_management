from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("reviews/<str:token>/", views.submit_review, name="submit"),
    path("sites/<uuid:site_id>/reviews/", views.manage_reviews, name="manage"),
    path(
        "sites/<uuid:site_id>/reviews/<uuid:review_id>/respond/",
        views.respond,
        name="respond",
    ),
    path(
        "sites/<uuid:site_id>/reviews/<uuid:review_id>/report/",
        views.report,
        name="report",
    ),
]
