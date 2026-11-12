import datetime

from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.blog.models import PostStatus
from apps.core.models import NotFoundLog
from apps.public.models import Redirect

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class RedirectModelValidationTests(TestCase):
    def test_relative_path_gets_leading_slash(self):
        entry = Redirect(old_path="old-page", new_path="/new-page/")
        entry.clean()
        self.assertEqual(entry.old_path, "/old-page")

    def test_javascript_scheme_rejected(self):
        entry = Redirect(old_path="/old/", new_path="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_data_scheme_rejected(self):
        entry = Redirect(old_path="/old/", new_path="data:text/html,<script>alert(1)</script>")
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_old_path_cannot_be_an_absolute_url(self):
        entry = Redirect(old_path="https://example.com/old/", new_path="/new/")
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_new_path_may_be_an_external_https_url(self):
        entry = Redirect(old_path="/old/", new_path="https://example.com/moved/")
        entry.clean()  # should not raise
        self.assertEqual(entry.new_path, "https://example.com/moved/")

    def test_self_redirect_rejected(self):
        entry = Redirect(old_path="/same/", new_path="/same/")
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_direct_loop_rejected(self):
        Redirect.objects.create(old_path="/b/", new_path="/a/")
        entry = Redirect(old_path="/a/", new_path="/b/")
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_transitive_loop_rejected(self):
        # /a/ -> /b/ -> /c/ -> back to /a/ would be a loop.
        Redirect.objects.create(old_path="/a/", new_path="/b/")
        Redirect.objects.create(old_path="/b/", new_path="/c/")
        entry = Redirect(old_path="/c/", new_path="/a/")
        with self.assertRaises(ValidationError):
            entry.clean()

    def test_chain_without_loop_is_allowed(self):
        Redirect.objects.create(old_path="/a/", new_path="/b/")
        entry = Redirect(old_path="/z/", new_path="/a/")
        entry.clean()  # should not raise

    def test_duplicate_old_path_rejected_by_unique_constraint(self):
        Redirect.objects.create(old_path="/dup/", new_path="/one/")
        with self.assertRaises(ValidationError):
            Redirect.objects.create(old_path="/dup/", new_path="/two/")


class RedirectMiddlewareTests(TestCase):
    def test_301_redirect_served_for_matching_old_path(self):
        Redirect.objects.create(old_path="/old-permanent/", new_path="/new-permanent/", status_code=301)
        response = self.client.get("/old-permanent/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/new-permanent/")

    def test_302_redirect_served_for_matching_old_path(self):
        Redirect.objects.create(old_path="/old-temp/", new_path="/new-temp/", status_code=302)
        response = self.client.get("/old-temp/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/new-temp/")

    def test_redirect_to_external_url(self):
        Redirect.objects.create(old_path="/moved-away/", new_path="https://external.example.com/", status_code=301)
        response = self.client.get("/moved-away/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "https://external.example.com/")

    def test_genuine_404_is_recorded_in_not_found_log(self):
        self.client.get("/nothing-matches-this-path/")
        self.assertTrue(NotFoundLog.objects.filter(path="/nothing-matches-this-path/").exists())

    def test_repeated_404_increments_hit_count(self):
        self.client.get("/repeated-missing-path/")
        self.client.get("/repeated-missing-path/")
        self.client.get("/repeated-missing-path/")
        entry = NotFoundLog.objects.get(path="/repeated-missing-path/")
        self.assertEqual(entry.hit_count, 3)

    def test_static_media_404s_are_not_logged(self):
        self.client.get("/static/does-not-exist.css")
        self.assertFalse(NotFoundLog.objects.filter(path="/static/does-not-exist.css").exists())

    def test_404_matched_by_redirect_does_not_appear_in_not_found_log(self):
        Redirect.objects.create(old_path="/handled/", new_path="/blog/")
        self.client.get("/handled/")
        self.assertFalse(NotFoundLog.objects.filter(path="/handled/").exists())


class SlugChangeAutoRedirectTests(TestCase):
    def test_record_slug_redirect_creates_entry(self):
        from apps.public.services import record_slug_redirect

        record_slug_redirect("/blog/old-slug/", "/blog/new-slug/")

        entry = Redirect.objects.get(old_path="/blog/old-slug/")
        self.assertEqual(entry.new_path, "/blog/new-slug/")
        self.assertTrue(entry.is_auto)
        self.assertEqual(entry.status_code, 301)

    def test_record_slug_redirect_is_idempotent(self):
        from apps.public.services import record_slug_redirect

        record_slug_redirect("/blog/old-slug/", "/blog/new-slug/")
        record_slug_redirect("/blog/old-slug/", "/blog/new-slug/")

        self.assertEqual(Redirect.objects.filter(old_path="/blog/old-slug/").count(), 1)

    def test_record_slug_redirect_repoints_existing_chain(self):
        from apps.public.services import record_slug_redirect

        # /blog/a/ -> /blog/b/ already exists (b was renamed once before).
        record_slug_redirect("/blog/a/", "/blog/b/")
        # Now b is renamed to c: the old a->b entry must be repointed to c,
        # not left dangling as a two-hop chain.
        record_slug_redirect("/blog/b/", "/blog/c/")

        self.assertEqual(Redirect.objects.get(old_path="/blog/a/").new_path, "/blog/c/")
        self.assertEqual(Redirect.objects.get(old_path="/blog/b/").new_path, "/blog/c/")

    def test_record_slug_redirect_removes_reverse_pair(self):
        from apps.public.services import record_slug_redirect

        # A previous redirect said c -> a. Now a is renamed back to c,
        # which would be a self-redirect/loop unless the reverse is cleared.
        Redirect.objects.create(old_path="/blog/c/", new_path="/blog/a/")
        record_slug_redirect("/blog/a/", "/blog/c/")

        self.assertFalse(Redirect.objects.filter(old_path="/blog/c/", new_path="/blog/a/").exists())
        self.assertEqual(Redirect.objects.get(old_path="/blog/a/").new_path, "/blog/c/")

    def test_editing_published_post_slug_creates_working_redirect(self):
        from apps.accounts.roles import AUTHOR

        author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(author, "add_post", "change_post", "view_post", "publish_post")
        post = published_post(author, title="Original Title", slug="original-slug")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        old_url = post.get_absolute_url()
        self.client.post(reverse("dashboard:post-edit", args=[post.pk]), {
            "title": "Original Title", "slug": "renamed-slug", "excerpt": "",
            "content": "<p>Body</p>", "category": "", "tags": [],
        })

        response = self.client.get(old_url)
        post.refresh_from_db()
        self.assertRedirects(response, post.get_absolute_url(), status_code=301, target_status_code=200)
        self.assertEqual(post.slug, "renamed-slug")

    def test_editing_draft_post_slug_does_not_create_redirect(self):
        from apps.accounts.roles import AUTHOR

        author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(author, "add_post", "change_post", "view_post")
        post = make_post(author, title="Draft", slug="draft-original-slug", status=PostStatus.DRAFT)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        self.client.post(reverse("dashboard:post-edit", args=[post.pk]), {
            "title": "Draft", "slug": "draft-renamed-slug", "excerpt": "",
            "content": "<p>Body</p>", "category": "", "tags": [],
        })

        self.assertFalse(Redirect.objects.filter(old_path="/blog/draft-original-slug/").exists())


class RedirectDashboardCRUDTests(TestCase):
    def setUp(self):
        super().setUp()
        self.entry = Redirect.objects.create(old_path="/existing/", new_path="/blog/")

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:redirect-list"))
        self.assertEqual(response.status_code, 302)

    def test_user_without_permission_gets_403(self):
        make_user("nobody@example.com", "nobody")
        self.client.login(username="nobody@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:redirect-list"))
        self.assertEqual(response.status_code, 403)

    def test_user_with_permission_can_list(self):
        user = make_user("seo-editor@example.com", "seoeditor")
        grant_perms(user, "view_redirect", app_label="public")
        self.client.login(username="seo-editor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:redirect-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/existing/")

    def test_user_with_permission_can_create(self):
        user = make_user("seo-editor@example.com", "seoeditor")
        grant_perms(user, "add_redirect", app_label="public")
        self.client.login(username="seo-editor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:redirect-create"), {
            "old_path": "/brand-new/", "new_path": "/blog/", "status_code": 301,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Redirect.objects.filter(old_path="/brand-new/").exists())

    def test_create_without_permission_is_forbidden(self):
        make_user("nobody@example.com", "nobody")
        self.client.login(username="nobody@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:redirect-create"), {
            "old_path": "/should-not-exist/", "new_path": "/blog/", "status_code": 301,
        })
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Redirect.objects.filter(old_path="/should-not-exist/").exists())

    def test_loop_creation_shows_form_error_not_500(self):
        user = make_user("seo-editor@example.com", "seoeditor")
        grant_perms(user, "add_redirect", app_label="public")
        self.client.login(username="seo-editor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:redirect-create"), {
            "old_path": "/blog/", "new_path": "/existing/", "status_code": 301,
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Redirect.objects.filter(old_path="/blog/").exists())

    def test_user_with_permission_can_delete(self):
        user = make_user("seo-editor@example.com", "seoeditor")
        grant_perms(user, "delete_redirect", app_label="public")
        self.client.login(username="seo-editor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:redirect-delete", args=[self.entry.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Redirect.objects.filter(pk=self.entry.pk).exists())


class RedirectRateLimitingTests(TestCase):
    """A staffer with add_redirect could otherwise create unlimited
    external-URL redirects in a loop — cheap abuse vector (phishing,
    SEO spam) worth the same per-user throttle every other admin
    mutation endpoint already gets (see apps/dashboard/views/posts.py etc).
    """

    @override_settings(RATELIMIT_ENABLE=True)
    def test_redirect_create_is_rate_limited(self):
        from django.core.cache import cache

        cache.clear()
        user = make_user("seo-editor@example.com", "seoeditor")
        grant_perms(user, "add_redirect", app_label="public")
        self.client.login(username="seo-editor@example.com", password=DEFAULT_PASSWORD)

        responses = [
            self.client.post(reverse("dashboard:redirect-create"), {
                "old_path": f"/rl-test-{i}/", "new_path": "/blog/", "status_code": 301,
            })
            for i in range(35)
        ]

        self.assertIn(403, [r.status_code for r in responses])
