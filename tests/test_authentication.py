from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserStatus

User = get_user_model()


def make_user(email="writer@example.com", username="writer", password="a-strong-password-123", **extra):
    return User.objects.create_user(email=email, username=username, password=password, **extra)


class LoginTests(TestCase):
    def setUp(self):
        self.password = "a-strong-password-123"
        self.user = make_user(password=self.password)

    def test_login_works_with_valid_credentials(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.password},
        )

        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_invalid_login_fails(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": "wrong-password"},
        )

        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(response.status_code, 200)

    def test_logout_works(self):
        self.client.login(username=self.user.email, password=self.password)
        self.client.post(reverse("accounts:logout"))

        response = self.client.get(reverse("public:home"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_password_is_hashed_not_stored_in_plaintext(self):
        self.assertNotEqual(self.user.password, self.password)
        self.assertTrue(self.user.password.startswith("pbkdf2_") or "$" in self.user.password)
        self.assertTrue(self.user.check_password(self.password))

    def test_protected_admin_area_rejects_guests(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)


class AccountStatusTests(TestCase):
    def setUp(self):
        self.password = "a-strong-password-123"

    def test_inactive_user_cannot_log_in(self):
        make_user(email="inactive@example.com", username="inactive", password=self.password, status=UserStatus.INACTIVE)

        can_login = self.client.login(username="inactive@example.com", password=self.password)

        self.assertFalse(can_login)

    def test_suspended_user_cannot_log_in(self):
        make_user(email="suspended@example.com", username="suspended", password=self.password, status=UserStatus.SUSPENDED)

        can_login = self.client.login(username="suspended@example.com", password=self.password)

        self.assertFalse(can_login)

    def test_active_user_can_log_in(self):
        make_user(email="active@example.com", username="active", password=self.password, status=UserStatus.ACTIVE)

        can_login = self.client.login(username="active@example.com", password=self.password)

        self.assertTrue(can_login)
