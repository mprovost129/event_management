from django.urls import path

from . import views

app_name = "sites"

urlpatterns = [
    path("dashboard/", views.account_dashboard, name="account_dashboard"),
    path("start/", views.onboarding, name="onboarding"),
    path("sites/<uuid:site_id>/", views.dashboard, name="dashboard"),
    path("sites/<uuid:site_id>/quick-start/", views.quick_start, name="quick_start"),
    path(
        "sites/<uuid:site_id>/launch/",
        views.launch_center,
        name="launch_center",
    ),
    path("sites/<uuid:site_id>/reports/", views.reports, name="reports"),
    path("sites/<uuid:site_id>/export/", views.export_data, name="export_data"),
    path("sites/<uuid:site_id>/managers/", views.add_manager, name="add_manager"),
    path(
        "sites/<uuid:site_id>/managers/<uuid:role_id>/remove/",
        views.remove_manager,
        name="remove_manager",
    ),
]
