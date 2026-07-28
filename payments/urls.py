from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("commerce/stripe/connect/", views.connect_webhook, name="connect_webhook"),
    path("sites/<uuid:site_id>/commerce/", views.manage, name="manage"),
    path(
        "sites/<uuid:site_id>/commerce/connect/",
        views.connect_start,
        name="connect_start",
    ),
    path(
        "sites/<uuid:site_id>/commerce/connect/refresh/",
        views.connect_refresh,
        name="connect_refresh",
    ),
    path(
        "sites/<uuid:site_id>/commerce/connect/sync/",
        views.connect_sync,
        name="connect_sync",
    ),
    path(
        "sites/<uuid:site_id>/commerce/occurrences/<uuid:occurrence_id>/tickets/new/",
        views.ticket_type_create,
        name="ticket_type_create",
    ),
    path(
        "checkout/tickets/<str:token>/", views.ticket_checkout, name="ticket_checkout"
    ),
    path(
        "sites/<uuid:site_id>/commerce/tickets/<uuid:ticket_type_id>/",
        views.ticket_type_edit,
        name="ticket_type_edit",
    ),
    path(
        "sites/<uuid:site_id>/commerce/orders/<uuid:order_id>/refund/",
        views.refund_order,
        name="refund_order",
    ),
    path(
        "sites/<uuid:site_id>/commerce/membership-plans/new/",
        views.membership_plan_create,
        name="membership_plan_create",
    ),
    path(
        "sites/<uuid:site_id>/commerce/membership-plans/<uuid:plan_id>/",
        views.membership_plan_edit,
        name="membership_plan_edit",
    ),
    path("memberships/", views.membership_plans, name="membership_plans"),
    path(
        "memberships/<uuid:plan_id>/join/",
        views.membership_join,
        name="membership_join",
    ),
]
