from django.urls import path

from . import views

app_name = "sites"

urlpatterns = [
    path("dashboard/", views.account_dashboard, name="account_dashboard"),
    path("start/", views.onboarding, name="onboarding"),
    path("sites/<uuid:site_id>/", views.dashboard, name="dashboard"),
    path("sites/<uuid:site_id>/managers/", views.add_manager, name="add_manager"),
    path(
        "sites/<uuid:site_id>/managers/<uuid:role_id>/remove/",
        views.remove_manager,
        name="remove_manager",
    ),
]
