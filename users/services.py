from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_verification_token


def send_verification_email(*, user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    verification_url = request.build_absolute_uri(
        reverse("users:verify_email", kwargs={"uidb64": uid, "token": token})
    )
    context = {
        "user": user,
        "verification_url": verification_url,
        "platform_name": settings.PLATFORM_NAME,
    }
    subject = render_to_string("users/email/verify_subject.txt", context).strip()
    body = render_to_string("users/email/verify_body.txt", context)
    return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
