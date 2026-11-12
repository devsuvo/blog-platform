from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.roles import AUTHOR, SUPER_ADMIN
from apps.blog.models import Post

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class XSSSanitizationTests(TestCase):
    def setUp(self):
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "view_post", "change_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_script_tags_are_stripped_on_create(self):
        self.client.post(reverse("dashboard:post-create"), {
            "title": "XSS attempt", "slug": "", "excerpt": "", "content": "<p>hi</p><script>alert(1)</script>",
            "category": "", "tags": [],
        })
        post = Post.objects.get()
        self.assertNotIn("<script", post.content)
        self.assertIn("<p>hi</p>", post.content)

    def test_event_handlers_and_js_urls_are_stripped(self):
        self.client.post(reverse("dashboard:post-create"), {
            "title": "XSS attempt 2", "slug": "", "excerpt": "", "content":
                '<img src="x.jpg" onerror="alert(1)"><a href="javascript:alert(1)">click</a>',
            "category": "", "tags": [],
        })
        post = Post.objects.get()
        self.assertNotIn("onerror", post.content)
        self.assertNotIn("javascript:", post.content)

    def test_autosave_also_sanitizes_content(self):
        import json

        post = make_post(self.author, title="Draft", slug="draft")
        response = self.client.post(
            reverse("dashboard:post-autosave", args=[post.pk]),
            data=json.dumps({"title": "Draft", "excerpt": "", "content": "<p>ok</p><script>alert(1)</script>"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        post.refresh_from_db()
        self.assertNotIn("<script", post.content)


class CSRFProtectionTests(TestCase):
    def test_post_publish_without_csrf_token_is_rejected(self):
        author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(author, "add_post", "view_post", "change_post", "publish_post")
        post = make_post(author, title="Draft", slug="draft")

        strict_client = Client(enforce_csrf_checks=True)
        strict_client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        response = strict_client.post(reverse("dashboard:post-publish", args=[post.pk]))

        self.assertEqual(response.status_code, 403)


class IDORTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com", "owner", role=AUTHOR)
        grant_perms(self.owner, "add_post", "view_post", "change_post", "delete_post", "publish_post")
        self.other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(self.other, "add_post", "view_post", "change_post", "delete_post", "publish_post")
        self.post = make_post(self.owner, title="Owner post", slug="owner-post")

    def test_cannot_edit_others_post_by_guessing_url(self):
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-edit", args=[self.post.pk]), {
            "title": "Hijacked", "slug": "owner-post", "content": "<p>Hijacked</p>",
        })
        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.title, "Owner post")

    def test_unauthorized_delete_blocked(self):
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-delete", args=[self.post.pk]))
        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertIsNone(self.post.deleted_at)

    def test_owner_can_delete_own_post(self):
        # "Delete" moves the post to trash (soft delete) — see
        # tests/test_post_trash.py for the full trash/restore/permanent-
        # delete lifecycle. The row still exists; deleted_at is set.
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-delete", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.deleted_at)
