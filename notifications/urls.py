from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.notification_list, name="list"),
    path("notifications/read-all/", views.mark_all_read, name="mark_all_read"),
    path(
        "notifications/<uuid:notification_id>/read/", views.mark_read, name="mark_read"
    ),
]
