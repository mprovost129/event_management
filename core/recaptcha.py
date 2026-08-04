import logging

import requests
from django.conf import settings

from .rate_limits import client_address

logger = logging.getLogger(__name__)

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"
TIMEOUT_SECONDS = 5


def recaptcha_configured():
    return bool(settings.RECAPTCHA_SITE_KEY and settings.RECAPTCHA_SECRET_KEY)


def verify_recaptcha(request, *, action):
    """Best-effort reCAPTCHA v3 check for the given form action.

    Returns True when the submission should proceed - either because it
    passed, because reCAPTCHA is not configured, or because Google's
    verification endpoint is unreachable. A hard fail on a Google outage
    would turn that outage into a self-inflicted block of every public
    form, which is worse than letting a few unscored submissions through.
    """
    if not recaptcha_configured():
        return True
    token = request.POST.get("recaptcha_token", "")
    if not token:
        return False

    try:
        response = requests.post(
            VERIFY_URL,
            data={
                "secret": settings.RECAPTCHA_SECRET_KEY,
                "response": token,
                "remoteip": client_address(request),
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("reCAPTCHA verification unavailable; allowing submission")
        return True

    if not result.get("success") or result.get("action") != action:
        return False
    return result.get("score", 0) >= settings.RECAPTCHA_SCORE_THRESHOLD
