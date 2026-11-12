import datetime

from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.blog.models import PostStatus
from apps.public.models import ContactMessage

from .base import CacheClearingTestCase as TestCase
from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class SearchSecurityTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_search_query_is_html_escaped_in_response(self):
        response = self.client.get("/search/", {"q": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_search_sql_like_query_does_not_error(self):
        # ORM-parameterized, so this should just return zero results, not 500.
        response = self.client.get("/search/", {"q": "'; DROP TABLE blog_post; --"})
        self.assertEqual(response.status_code, 200)

    def test_search_never_returns_draft_content(self):
        make_post(self.author, title="Confidential Draft Title", slug="confidential-draft", status=PostStatus.DRAFT)
        response = self.client.get("/search/", {"q": "Confidential"})
        self.assertNotContains(response, "Confidential Draft Title")

    def test_overly_long_query_is_truncated_not_rejected(self):
        response = self.client.get("/search/", {"q": "a" * 5000})
        self.assertEqual(response.status_code, 200)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_search_is_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        responses = [self.client.get("/search/", {"q": "test"}) for _ in range(35)]
        self.assertIn(403, [r.status_code for r in responses])


class ContactFormSecurityTests(TestCase):
    def _valid_payload(self, **overrides):
        payload = {
            "name": "Jane Doe", "email": "jane@example.com", "subject": "Hello",
            "message": "A normal message.", "website": "",
        }
        payload.update(overrides)
        return payload

    def test_csrf_required(self):
        strict_client = Client(enforce_csrf_checks=True)
        response = strict_client.post(reverse("public:contact"), self._valid_payload())
        self.assertEqual(response.status_code, 403)

    def test_honeypot_rejects_bot_submission(self):
        response = self.client.post(reverse("public:contact"), self._valid_payload(website="http://spam.example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactMessage.objects.exists())

    def test_valid_submission_is_saved_and_emailed(self):
        response = self.client.post(reverse("public:contact"), self._valid_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_html_in_message_is_stripped(self):
        self.client.post(reverse("public:contact"), self._valid_payload(
            message="<script>alert(1)</script>Hello <b>there</b>"
        ))
        message = ContactMessage.objects.get()
        self.assertNotIn("<script>", message.message)
        self.assertNotIn("<b>", message.message)

    def test_invalid_email_rejected(self):
        response = self.client.post(reverse("public:contact"), self._valid_payload(email="not-an-email"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactMessage.objects.exists())

    @override_settings(RATELIMIT_ENABLE=True)
    def test_contact_form_is_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        responses = [self.client.post(reverse("public:contact"), self._valid_payload()) for _ in range(8)]
        self.assertIn(403, [r.status_code for r in responses])


class PreviewProtectionTests(TestCase):
    """Cross-check with Step 3: the admin preview URL must stay behind
    login, and the public URL must never serve non-published content —
    there should be no way to view a draft without authorization.
    """

    def test_draft_not_reachable_via_any_public_url_shape(self):
        author = make_user("author@example.com", "author")
        post = make_post(author, title="Draft", slug="draft-security-test", status=PostStatus.DRAFT)

        for path in [post.get_absolute_url(), f"/blog/{post.slug}/?preview=1", f"/blog/{post.slug}/?status=published"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404, path)

    def test_admin_preview_requires_login(self):
        author = make_user("author@example.com", "author")
        post = make_post(author, title="Draft", slug="draft-needs-login", status=PostStatus.DRAFT)

        response = self.client.get(reverse("dashboard:post-preview", args=[post.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
