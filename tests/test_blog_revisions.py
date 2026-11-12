from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import AUTHOR
from apps.blog.models import PostRevision

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class RevisionCreationTests(TestCase):
    def setUp(self):
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "view_post", "change_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        self.post = make_post(self.author, title="Original title", slug="original-title", content="<p>Original</p>")

    def test_editing_content_creates_a_revision(self):
        self.client.post(reverse("dashboard:post-edit", args=[self.post.pk]), {
            "title": "Original title", "slug": "original-title", "excerpt": "",
            "content": "<p>Changed</p>", "category": "", "tags": [],
        })

        self.assertEqual(self.post.revisions.count(), 1)
        revision = self.post.revisions.first()
        self.assertEqual(revision.content, "<p>Original</p>")
        self.post.refresh_from_db()
        self.assertEqual(self.post.content, "<p>Changed</p>")

    def test_saving_without_changes_does_not_create_a_revision(self):
        self.client.post(reverse("dashboard:post-edit", args=[self.post.pk]), {
            "title": "Original title", "slug": "original-title", "excerpt": "",
            "content": "<p>Original</p>", "category": "", "tags": [],
        })
        self.assertEqual(self.post.revisions.count(), 0)

    def test_restore_reverts_content_and_snapshots_pre_restore_state(self):
        self.client.post(reverse("dashboard:post-edit", args=[self.post.pk]), {
            "title": "Original title", "slug": "original-title", "excerpt": "",
            "content": "<p>Changed</p>", "category": "", "tags": [],
        })
        revision = self.post.revisions.first()

        response = self.client.post(
            reverse("dashboard:post-revision-restore", args=[self.post.pk, revision.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.content, "<p>Original</p>")
        self.assertEqual(self.post.revisions.count(), 2)


class UnauthorizedRestoreTests(TestCase):
    def test_restore_blocked_for_user_without_edit_permission(self):
        owner = make_user("owner@example.com", "owner", role=AUTHOR)
        grant_perms(owner, "add_post", "view_post", "change_post")
        post = make_post(owner, title="T", slug="t", content="<p>A</p>")
        revision = PostRevision.objects.create(post=post, title="T", content="<p>Old</p>", author=owner)

        other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(other, "add_post", "view_post", "change_post")
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(
            reverse("dashboard:post-revision-restore", args=[post.pk, revision.pk])
        )

        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.content, "<p>A</p>")
