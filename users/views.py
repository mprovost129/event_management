from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.http import require_http_methods

from core.rate_limits import public_write_rate_limit
from ops.services import record_audit_event
from subscriptions.gateway import billing_options

from .forms import ProfileForm, ResendVerificationForm, SignupForm
from .models import User
from .services import send_verification_email
from .tokens import email_verification_token


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("account-signup")
def signup(request):
    if request.user.is_authenticated:
        return redirect("sites:account_dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        send_verification_email(user=user, request=request)
        messages.success(
            request,
            "Check your email to verify your account before signing in.",
        )
        return redirect("users:verification_sent")
    return render(
        request,
        "users/signup.html",
        {"form": form, "billing_options": billing_options()},
    )


def verification_sent(request):
    return render(request, "users/verification_sent.html")


def verify_email(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is None or not email_verification_token.check_token(user, token):
        return render(request, "users/verification_invalid.html", status=400)

    if not user.is_email_verified:
        user.email_verified_at = timezone.now()
        user.is_active = True
        user.save(update_fields=("email_verified_at", "is_active"))
        record_audit_event(
            action="account.email_verified",
            actor=user,
            target=user,
            request=request,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Your email is verified. Let's create your site.")
    return redirect("sites:onboarding")


@require_http_methods(["GET", "POST"])
@public_write_rate_limit("verification-resend")
def resend_verification(request):
    form = ResendVerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email=form.cleaned_data["email"]).first()
        if user and not user.is_email_verified:
            send_verification_email(user=user, request=request)
        messages.success(
            request,
            "If that address has an unverified account, a new link has been sent.",
        )
        return redirect("users:verification_sent")
    return render(request, "users/resend_verification.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    form = ProfileForm(
        request.POST or None, request.FILES or None, instance=request.user
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("users:profile")
    return render(request, "users/profile.html", {"form": form})
