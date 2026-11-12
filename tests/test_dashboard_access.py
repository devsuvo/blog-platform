from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserStatus
from apps.accounts.roles import SUPER_ADMIN

from .helpers import DEFAULT_PASSWORD, make_user


class DashboardAccessTests(TestCase):
    def test_guest_cannot_access_dashboard(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_authenticated_user_can_access_dashboard(self):
        make_user("author@example.com", "author", role="Author")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 200)

    def test_suspended_user_is_blocked_mid_session(self):
        user = make_user("editor@example.com", "editor", role="Editor")
        self.client.login(username="editor@example.com", password=DEFAULT_PASSWORD)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)

        user.status = UserStatus.SUSPENDED
        user.save(update_fields=["status", "is_active"])

        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_inactive_user_is_blocked_mid_session(self):
        user = make_user("author2@example.com", "author2", role="Author")
        self.client.login(username="author2@example.com", password=DEFAULT_PASSWORD)
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)

        user.status = UserStatus.INACTIVE
        user.save(update_fields=["status", "is_active"])

        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)

    def test_logout_works_from_admin_panel(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

        self.client.post(reverse("accounts:logout"))
        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
