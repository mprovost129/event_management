from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

handler400 = "core.error_views.bad_request"
handler403 = "core.error_views.permission_denied"
handler404 = "core.error_views.page_not_found"
handler500 = "core.error_views.server_error"

urlpatterns = [
    path("platform-admin/", admin.site.urls),
    path("", include("ops.urls")),
    path("accounts/", include("users.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("billing/", include("subscriptions.urls")),
    path("", include("payments.urls")),
    path("", include("communications.urls")),
    path("", include("content.urls")),
    path("", include("contacts.urls")),
    path("", include("events.urls")),
    path("", include("attendance.urls")),
    path("", include("reviews.urls")),
    path("", include("notifications.urls")),
    path("", include("workspace.urls")),
    path("", include("sites.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
