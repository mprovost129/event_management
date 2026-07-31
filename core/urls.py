from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("health/live/", views.health_live, name="health_live"),
    path("health/ready/", views.health_ready, name="health_ready"),
    path("help/", views.HelpView.as_view(), name="help"),
    path("legal/", views.LegalCenterView.as_view(), name="legal"),
    path(
        "privacy/",
        views.LegalPageView.as_view(document_key="privacy"),
        name="privacy",
    ),
    path(
        "terms/",
        views.LegalPageView.as_view(document_key="terms"),
        name="terms",
    ),
    path(
        "cookies/",
        views.LegalPageView.as_view(document_key="cookies"),
        name="cookies",
    ),
    path(
        "payments-cancellations-refunds/",
        views.LegalPageView.as_view(document_key="refunds"),
        name="refunds",
    ),
    path(
        "acceptable-use/",
        views.LegalPageView.as_view(document_key="acceptable_use"),
        name="acceptable_use",
    ),
    path(
        "data-retention/",
        views.LegalPageView.as_view(document_key="retention"),
        name="retention",
    ),
    path(
        "security/",
        views.LegalPageView.as_view(document_key="security"),
        name="security",
    ),
    path(
        "review-guidelines/",
        views.LegalPageView.as_view(document_key="review_guidelines"),
        name="review_guidelines",
    ),
    path("", views.HomeView.as_view(), name="home"),
]
