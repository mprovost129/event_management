from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("verification-sent/", views.verification_sent, name="verification_sent"),
    path(
        "verify/<uidb64>/<token>/",
        views.verify_email,
        name="verify_email",
    ),
    path(
        "resend-verification/",
        views.resend_verification,
        name="resend_verification",
    ),
]
