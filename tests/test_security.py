from django.contrib.auth import get_user_model
from django.test import Client, TestCase

User = get_user_model()


class CSRFProtectionTests(TestCase):
    def setUp(self):
        self.strict_client = Client(enforce_csrf_checks=True)

    def test_post_without_csrf_token_is_rejected(self):
        response = self.strict_client.post(
            "/accounts/login/",
            {"username": "someone@example.com", "password": "whatever"},
        )

        self.assertEqual(response.status_code, 403)


class ProductionSettingsSecurityTests(TestCase):
    """Import the real production settings module and assert its secure defaults.

    These are the values that matter once DEBUG is False; they must be safe
    even if an operator forgets to set the optional override env vars.
    """

    def test_production_settings_are_secure_by_default(self):
        from config.settings import production

        self.assertFalse(production.DEBUG)
        self.assertTrue(production.SESSION_COOKIE_SECURE)
        self.assertTrue(production.CSRF_COOKIE_SECURE)
        self.assertTrue(production.SECURE_SSL_REDIRECT)
        self.assertGreater(production.SECURE_HSTS_SECONDS, 0)
        self.assertTrue(production.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertTrue(production.SECURE_HSTS_PRELOAD)
        self.assertTrue(production.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(production.X_FRAME_OPTIONS, "DENY")
        self.assertEqual(production.SESSION_COOKIE_SAMESITE, "Lax")

    def test_development_settings_do_not_force_https(self):
        from config.settings import development

        self.assertTrue(development.DEBUG)
        self.assertFalse(development.SECURE_SSL_REDIRECT)
