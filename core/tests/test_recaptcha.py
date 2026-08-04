from unittest.mock import patch

import pytest
from django.test import RequestFactory, override_settings

from core.recaptcha import recaptcha_configured, verify_recaptcha


class FakeVerifyResponse:
    def __init__(self, result):
        self.result = result

    def raise_for_status(self):
        pass

    def json(self):
        return self.result


def _request(token=""):
    data = {"recaptcha_token": token} if token else {}
    return RequestFactory().post("/", data)


def test_recaptcha_not_configured_allows_any_submission():
    assert recaptcha_configured() is False
    assert verify_recaptcha(_request(), action="signup") is True


@override_settings(RECAPTCHA_SITE_KEY="site", RECAPTCHA_SECRET_KEY="secret")
def test_recaptcha_configured_rejects_missing_token():
    assert recaptcha_configured() is True
    assert verify_recaptcha(_request(token=""), action="signup") is False


@override_settings(
    RECAPTCHA_SITE_KEY="site",
    RECAPTCHA_SECRET_KEY="secret",
    RECAPTCHA_SCORE_THRESHOLD=0.5,
)
@pytest.mark.parametrize(
    ("result", "expected"),
    (
        ({"success": True, "action": "signup", "score": 0.9}, True),
        ({"success": True, "action": "signup", "score": 0.5}, True),
        ({"success": True, "action": "signup", "score": 0.4}, False),
        ({"success": False, "action": "signup", "score": 0.9}, False),
        ({"success": True, "action": "newsletter_signup", "score": 0.9}, False),
    ),
)
def test_recaptcha_configured_evaluates_score_and_action(result, expected):
    with patch("core.recaptcha.requests.post", return_value=FakeVerifyResponse(result)):
        assert verify_recaptcha(_request(token="abc"), action="signup") is expected


@override_settings(RECAPTCHA_SITE_KEY="site", RECAPTCHA_SECRET_KEY="secret")
def test_recaptcha_network_failure_fails_open():
    import requests

    with patch(
        "core.recaptcha.requests.post",
        side_effect=requests.ConnectionError("boom"),
    ):
        assert verify_recaptcha(_request(token="abc"), action="signup") is True
