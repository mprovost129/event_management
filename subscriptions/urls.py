from django.urls import path

from . import views

app_name = "subscriptions"

urlpatterns = [
    path("stripe/", views.stripe_webhook, name="stripe_webhook"),
    path("sites/<uuid:site_id>/checkout/", views.checkout, name="checkout"),
    path("sites/<uuid:site_id>/portal/", views.portal, name="portal"),
]
