from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class HealthCheckTests(SimpleTestCase):
    def test_health_check_returns_ok(self):
        response = self.client.get(reverse("core:health-check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_check_does_not_leak_internal_details(self):
        response = self.client.get(reverse("core:health-check"))

        body = response.json()
        self.assertEqual(set(body.keys()), {"status"})


class ReadinessCheckTests(TestCase):
    """Uses TestCase (not SimpleTestCase) — the readiness probe genuinely
    touches the database and cache, which SimpleTestCase forbids.
    """

    def test_ready_when_database_and_cache_are_reachable(self):
        response = self.client.get(reverse("core:readiness-check"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "database": True, "cache": True})

    def test_unavailable_when_database_is_unreachable(self):
        with patch("django.db.backends.utils.CursorWrapper.execute", side_effect=Exception("connection refused")):
            response = self.client.get(reverse("core:readiness-check"))

        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "unavailable")
        self.assertFalse(body["database"])

    def test_response_never_includes_credentials_or_hostnames(self):
        response = self.client.get(reverse("core:readiness-check"))

        body = response.json()
        self.assertEqual(set(body.keys()), {"status", "database", "cache"})
        for value in body.values():
            self.assertNotIsInstance(value, dict)


class RequestIDTests(SimpleTestCase):
    def test_response_carries_an_x_request_id_header(self):
        response = self.client.get(reverse("core:health-check"))
        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])

    def test_client_supplied_request_id_is_reused(self):
        response = self.client.get(reverse("core:health-check"), HTTP_X_REQUEST_ID="my-trace-id-123")
        self.assertEqual(response["X-Request-ID"], "my-trace-id-123")

    def test_unsafe_client_supplied_request_id_is_sanitized(self):
        response = self.client.get(reverse("core:health-check"), HTTP_X_REQUEST_ID="abc\r\nX-Injected: evil")
        self.assertNotIn("\r", response["X-Request-ID"])
        self.assertNotIn("\n", response["X-Request-ID"])
