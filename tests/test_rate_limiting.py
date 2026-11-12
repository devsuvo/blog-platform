from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.roles import SUPER_ADMIN

from .helpers import DEFAULT_PASSWORD, make_user


@override_settings(RATELIMIT_ENABLE=True)
class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_repeated_failed_logins_get_blocked(self):
        make_user("target@example.com", "target")

        responses = [
            self.client.post(reverse("accounts:login"), {"username": "target@example.com", "password": "wrong"})
            for _ in range(25)
        ]

        self.assertEqual(responses[-1].status_code, 403)


@override_settings(RATELIMIT_ENABLE=True)
class SensitiveActionRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

    def test_repeated_user_creation_gets_blocked(self):
        payload = {
            "first_name": "A", "last_name": "B", "username": "dupe",
            "bio": "", "status": "active", "role": "Author",
            "password1": "a-strong-password-456", "password2": "a-strong-password-456",
        }
        responses = []
        for i in range(25):
            responses.append(self.client.post(reverse("dashboard:user-create"), {**payload, "email": f"user{i}@example.com"}))

        self.assertEqual(responses[-1].status_code, 403)
