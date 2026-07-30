import uuid

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from core.middleware import PlatformSessionMiddleware, RequestContextMiddleware
from core.request_context import request_id_var, site_id_var


class RequestContextMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_generates_request_id_and_clears_context(self):
        seen = {}

        def get_response(request):
            seen["request_id"] = request_id_var.get()
            seen["site_id"] = site_id_var.get()
            return HttpResponse()

        middleware = RequestContextMiddleware(get_response)
        response = middleware(self.factory.get("/"))

        uuid.UUID(seen["request_id"])
        self.assertEqual(seen["site_id"], "-")
        self.assertEqual(response["X-Request-ID"], seen["request_id"])
        self.assertEqual(request_id_var.get(), "-")
        self.assertEqual(site_id_var.get(), "-")

    def test_accepts_only_bounded_safe_incoming_request_ids(self):
        middleware = RequestContextMiddleware(lambda request: HttpResponse())

        safe = middleware(
            self.factory.get("/", headers={"X-Request-ID": "request-12345678"})
        )
        unsafe = middleware(
            self.factory.get("/", headers={"X-Request-ID": "unsafe value\nheader"})
        )

        self.assertEqual(safe["X-Request-ID"], "request-12345678")
        self.assertNotEqual(unsafe["X-Request-ID"], "unsafe value\nheader")
        uuid.UUID(unsafe["X-Request-ID"])


@override_settings(
    ALLOWED_HOSTS=(".gatherhqs.com", ".onrender.com"),
    SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
)
class PlatformSessionMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def session_response(self, host):
        def get_response(request):
            request.session["authenticated"] = True
            return HttpResponse()

        return PlatformSessionMiddleware(get_response)(
            self.factory.get("/", headers={"host": host})
        )

    @override_settings(PLATFORM_DOMAIN="gatherhqs.com")
    def test_shares_session_cookie_across_platform_subdomains(self):
        response = self.session_response("kathy.gatherhqs.com")

        self.assertEqual(response.cookies["sessionid"]["domain"], ".gatherhqs.com")

    @override_settings(PLATFORM_DOMAIN="gatherhqs.com")
    def test_keeps_session_cookie_host_only_on_render_hostname(self):
        response = self.session_response("gather-hqs.onrender.com")

        self.assertEqual(response.cookies["sessionid"]["domain"], "")
