from django.urls import path

from . import views

app_name = "ops"

urlpatterns = [
    path("platform-ops/", views.dashboard, name="dashboard"),
    path(
        "platform-ops/sites/<uuid:site_id>/support/",
        views.support_grant,
        name="support_grant",
    ),
    path(
        "platform-ops/sites/<uuid:site_id>/snapshot/",
        views.support_snapshot,
        name="support_snapshot",
    ),
    path(
        "platform-ops/sites/<uuid:site_id>/suspend/",
        views.suspend_site,
        name="suspend_site",
    ),
    path(
        "platform-ops/sites/<uuid:site_id>/deletion/",
        views.deletion_request,
        name="deletion_request",
    ),
    path(
        "platform-ops/deletions/<uuid:deletion_id>/approve/",
        views.deletion_approve,
        name="deletion_approve",
    ),
    path(
        "platform-ops/deletions/<uuid:deletion_id>/cancel/",
        views.deletion_cancel,
        name="deletion_cancel",
    ),
    path(
        "platform-ops/reviews/<uuid:review_id>/<str:action>/",
        views.moderate,
        name="moderate_review",
    ),
]
