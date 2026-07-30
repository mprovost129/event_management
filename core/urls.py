from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("health/live/", views.health_live, name="health_live"),
    path("health/ready/", views.health_ready, name="health_ready"),
    path(
        "privacy/",
        views.LegalPageView.as_view(extra_context={"document": "privacy"}),
        name="privacy",
    ),
    path(
        "terms/",
        views.LegalPageView.as_view(extra_context={"document": "terms"}),
        name="terms",
    ),
    path(
        "acceptable-use/",
        views.LegalPageView.as_view(extra_context={"document": "acceptable_use"}),
        name="acceptable_use",
    ),
    path(
        "review-guidelines/",
        views.LegalPageView.as_view(extra_context={"document": "review_guidelines"}),
        name="review_guidelines",
    ),
    path("", views.HomeView.as_view(), name="home"),
]
