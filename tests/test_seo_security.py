import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR
from apps.blog.models import Post, PostStatus
from apps.public.models import Redirect
from apps.public.seo import safe_json_ld

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class CanonicalURLSecurityTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "view_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def _post_data(self, **overrides):
        data = {
            "title": "Canonical Test", "slug": "canonical-security-test", "excerpt": "",
            "content": "<p>Body</p>", "category": "", "tags": [],
        }
        data.update(overrides)
        return data

    def test_javascript_scheme_canonical_url_rejected(self):
        # Blocked by URLField's own scheme validation before our custom
        # javascript:/data:/vbscript: check even runs — the field simply
        # isn't a valid URL by Django's rules, so no post is ever created.
        response = self.client.post(
            reverse("dashboard:post-create"), self._post_data(canonical_url="javascript:alert(1)"),
        )
        self.assertEqual(response.status_code, 200)  # re-renders form with error, no redirect
        self.assertContains(response, "valid URL")
        self.assertFalse(Post.objects.filter(slug="canonical-security-test").exists())

    def test_data_scheme_canonical_url_rejected(self):
        response = self.client.post(
            reverse("dashboard:post-create"),
            self._post_data(canonical_url="data:text/html,<script>alert(1)</script>"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid URL")
        self.assertFalse(Post.objects.filter(slug="canonical-security-test").exists())

    def test_schemeless_canonical_url_is_normalized_to_http(self):
        # Django's URLField prepends http:// to schemeless input rather
        # than rejecting it outright — still a safe, well-formed URL.
        response = self.client.post(
            reverse("dashboard:post-create"), self._post_data(canonical_url="example.com/not-a-full-url"),
        )
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(slug="canonical-security-test")
        self.assertEqual(post.canonical_url, "http://example.com/not-a-full-url")

    def test_valid_https_canonical_url_is_accepted(self):
        response = self.client.post(
            reverse("dashboard:post-create"),
            self._post_data(canonical_url="https://example.com/original-source/"),
        )
        self.assertEqual(response.status_code, 302)


class RedirectSecurityTests(TestCase):
    def test_javascript_scheme_redirect_rejected_at_model_level(self):
        from django.core.exceptions import ValidationError

        entry = Redirect(old_path="/xss-attempt/", new_path="javascript:alert(document.cookie)")
        with self.assertRaises(ValidationError):
            entry.save()

    def test_unauthenticated_cannot_create_redirect(self):
        response = self.client.post(reverse("dashboard:redirect-create"), {
            "old_path": "/hijacked/", "new_path": "https://evil.example.com/", "status_code": 301,
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertFalse(Redirect.objects.filter(old_path="/hijacked/").exists())

    def test_low_privilege_user_cannot_create_redirect(self):
        make_user("author@example.com", "author", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:redirect-create"), {
            "old_path": "/hijacked-2/", "new_path": "https://evil.example.com/", "status_code": 301,
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Redirect.objects.filter(old_path="/hijacked-2/").exists())


class JSONLDSecurityTests(TestCase):
    def test_safe_json_ld_escapes_script_close_tag(self):
        payload = {"headline": "</script><img src=x onerror=alert(1)>"}
        rendered = safe_json_ld(payload)
        self.assertNotIn("</script>", rendered)

    def test_post_title_with_html_is_escaped_in_json_ld(self):
        author = make_user("author@example.com", "author")
        post = published_post(
            author, title='XSS Attempt </script><script>alert(1)</script>', slug="xss-json-ld-post",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertNotIn("<script>alert(1)</script>", response.content.decode())


class IndexabilityBoundaryTests(TestCase):
    """Content that must never be indexed, regardless of how it's reached."""

    def test_draft_post_returns_404_not_a_noindex_page(self):
        author = make_user("author@example.com", "author")
        post = make_post(author, title="Draft", slug="security-draft", status=PostStatus.DRAFT)
        response = self.client.get(post.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_preview_url_is_noindex_and_requires_auth(self):
        author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(author, "view_post")
        post = make_post(author, title="Preview Me", slug="security-preview", status=PostStatus.DRAFT)

        anon_response = self.client.get(reverse("dashboard:post-preview", args=[post.pk]))
        self.assertEqual(anon_response.status_code, 302)

        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:post-preview", args=[post.pk]))
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_admin_login_page_is_noindex(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, 'content="noindex, nofollow"')

    def test_search_results_page_is_noindex(self):
        response = self.client.get("/search/", {"q": "anything"})
        self.assertContains(response, 'content="noindex, follow"')
