import uuid

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from core.middleware import RequestContextMiddleware
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
