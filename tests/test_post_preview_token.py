import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR
from apps.blog.models import Post, PostPreviewToken, PostStatus

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class PreviewTokenGenerationTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "view_post")
        self.post = make_post(self.author, title="Draft Post", slug="draft-post", status=PostStatus.DRAFT)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_creating_a_preview_link_requires_edit_permission(self):
        response = self.client.post(reverse("dashboard:post-preview-link-create", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PostPreviewToken.objects.filter(post=self.post).count(), 1)

    def test_token_is_not_derived_from_post_id_slug_or_time(self):
        """Not a substring check (a random string can coincidentally
        contain a short digit sequence) — this proves the token isn't a
        *deterministic function* of the post's public attributes: two
        tokens for the exact same post, generated back to back, must
        still come out different, because they're independently random.
        """
        self.client.post(reverse("dashboard:post-preview-link-create", args=[self.post.pk]))
        self.client.post(reverse("dashboard:post-preview-link-create", args=[self.post.pk]))
        tokens = list(PostPreviewToken.objects.filter(post=self.post).values_list("token", flat=True))

        self.assertEqual(len(tokens), 2)
        self.assertNotEqual(tokens[0], tokens[1])
        for token in tokens:
            self.assertNotEqual(token, str(self.post.pk))
            self.assertNotEqual(token, self.post.slug)
            self.assertGreaterEqual(len(token), 32)

    def test_default_expiry_is_thirty_minutes(self):
        before = timezone.now()
        self.client.post(reverse("dashboard:post-preview-link-create", args=[self.post.pk]))
        token = PostPreviewToken.objects.get(post=self.post)

        delta = token.expires_at - before
        self.assertGreater(delta, datetime.timedelta(minutes=29))
        self.assertLess(delta, datetime.timedelta(minutes=31))

    def test_other_user_cannot_create_a_preview_link_for_someone_elses_post(self):
        other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(other, "view_post")
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-preview-link-create", args=[self.post.pk]))

        self.assertEqual(response.status_code, 403)


class TokenPreviewPublicAccessTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")
        self.post = make_post(self.author, title="Unpublished Draft", slug="unpublished-draft", status=PostStatus.DRAFT)

    def test_valid_token_shows_the_post_without_login(self):
        token = PostPreviewToken.generate(self.post, created_by=self.author)

        response = self.client.get(reverse("public:token-preview", args=[token.token]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unpublished Draft")

    def test_unknown_token_404s(self):
        response = self.client.get(reverse("public:token-preview", args=["not-a-real-token"]))
        self.assertEqual(response.status_code, 404)

    def test_expired_token_404s(self):
        token = PostPreviewToken.generate(self.post, created_by=self.author, minutes=30)
        PostPreviewToken.objects.filter(pk=token.pk).update(expires_at=timezone.now() - datetime.timedelta(minutes=1))

        response = self.client.get(reverse("public:token-preview", args=[token.token]))

        self.assertEqual(response.status_code, 404)

    def test_preview_is_always_noindex_nofollow(self):
        token = PostPreviewToken.generate(self.post, created_by=self.author)

        response = self.client.get(reverse("public:token-preview", args=[token.token]))

        self.assertContains(response, 'content="noindex, nofollow"')

    def test_preview_never_appears_in_sitemap(self):
        token = PostPreviewToken.generate(self.post, created_by=self.author)
        response = self.client.get("/sitemap-posts.xml")
        self.assertNotContains(response, token.token)
        self.assertNotContains(response, self.post.slug)

    def test_preview_never_appears_in_rss(self):
        PostPreviewToken.generate(self.post, created_by=self.author)
        response = self.client.get(reverse("public:feed"))
        self.assertNotContains(response, "Unpublished Draft")

    def test_preview_view_does_not_increment_view_count(self):
        token = PostPreviewToken.generate(self.post, created_by=self.author)
        self.client.get(reverse("public:token-preview", args=[token.token]))

        self.post.refresh_from_db()
        self.assertEqual(self.post.views_count, 0)

    def test_preview_is_rate_limited(self):
        from django.core.cache import cache
        from django.test import override_settings

        token = PostPreviewToken.generate(self.post, created_by=self.author)
        with override_settings(RATELIMIT_ENABLE=True):
            cache.clear()
            responses = [
                self.client.get(reverse("public:token-preview", args=[token.token])) for _ in range(25)
            ]
        self.assertIn(403, [r.status_code for r in responses])
