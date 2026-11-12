from django.urls import reverse

from apps.accounts.roles import ADMIN, SUPER_ADMIN

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, make_user


class SystemStatusAccessTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:system-status"))
        self.assertEqual(response.status_code, 302)

    def test_regular_user_is_redirected_not_500(self):
        make_user("regular@example.com", "regular")
        self.client.login(username="regular@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:system-status"))

        self.assertEqual(response.status_code, 302)

    def test_admin_role_staff_but_not_superuser_is_denied(self):
        # Admin is is_staff=True but not is_superuser — this page is
        # intentionally superuser-only (it surfaces cache backend / Celery
        # config, not just ordinary content-management data).
        make_user("staffer@example.com", "staffer", role=ADMIN)
        self.client.login(username="staffer@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:system-status"))

        self.assertEqual(response.status_code, 302)

    def test_superuser_can_view(self):
        make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:system-status"))

        self.assertEqual(response.status_code, 200)


class SystemStatusContentTests(TestCase):
    def setUp(self):
        super().setUp()
        make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

    def test_shows_healthy_database_and_cache(self):
        response = self.client.get(reverse("dashboard:system-status"))

        self.assertContains(response, "Healthy")
        self.assertTrue(response.context["database"]["ok"])
        self.assertTrue(response.context["cache"]["ok"])

    def test_shows_django_and_python_versions(self):
        import django
        import platform

        response = self.client.get(reverse("dashboard:system-status"))

        self.assertContains(response, django.get_version())
        self.assertContains(response, platform.python_version())

    def test_lists_seeded_periodic_tasks(self):
        response = self.client.get(reverse("dashboard:system-status"))

        self.assertContains(response, "Publish scheduled posts")
        self.assertContains(response, "Cleanup old data")

    def test_does_not_leak_redis_url_or_credentials(self):
        response = self.client.get(reverse("dashboard:system-status"))
        content = response.content.decode()
        self.assertNotIn("redis://", content)
        self.assertNotIn("SECRET_KEY", content)
