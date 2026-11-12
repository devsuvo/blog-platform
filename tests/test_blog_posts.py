from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import AUTHOR, SUPER_ADMIN
from apps.blog.models import Post

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class PostCreationTests(TestCase):
    def setUp(self):
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "view_post", "change_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_authorized_user_can_create_post(self):
        response = self.client.post(reverse("dashboard:post-create"), {
            "title": "My First Post", "slug": "", "excerpt": "", "content": "<p>Body</p>",
            "category": "", "tags": [], "meta_title": "", "meta_description": "",
            "canonical_url": "", "og_title": "", "og_description": "",
        })

        self.assertEqual(response.status_code, 302)
        post = Post.objects.get()
        self.assertEqual(post.author, self.author)
        self.assertEqual(post.status, "draft")
        self.assertEqual(post.slug, "my-first-post")

    def test_title_is_required(self):
        response = self.client.post(reverse("dashboard:post-create"), {
            "title": "", "slug": "", "excerpt": "", "content": "<p>Body</p>",
            "category": "", "tags": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_content_is_required(self):
        response = self.client.post(reverse("dashboard:post-create"), {
            "title": "No content here", "slug": "", "excerpt": "", "content": "",
            "category": "", "tags": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.exists())

    def test_slug_must_be_unique(self):
        make_post(self.author, title="Existing", slug="existing")
        response = self.client.post(reverse("dashboard:post-create"), {
            "title": "New title", "slug": "existing", "excerpt": "", "content": "<p>Body</p>",
            "category": "", "tags": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already in use")
        self.assertEqual(Post.objects.count(), 1)


class UnauthorizedPostCreationTests(TestCase):
    def test_user_without_permission_cannot_create_post(self):
        make_user("plain@example.com", "plain", role=AUTHOR)
        self.client.login(username="plain@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:post-create"))
        self.assertEqual(response.status_code, 403)


class ObjectLevelEditPermissionTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner@example.com", "owner", role=AUTHOR)
        grant_perms(self.owner, "add_post", "view_post", "change_post")
        self.other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(self.other, "add_post", "view_post", "change_post")
        self.post = make_post(self.owner, title="Owner's post", slug="owners-post")

    def test_author_can_edit_own_draft(self):
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:post-edit", args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)

    def test_author_cannot_edit_others_post_without_broad_permission(self):
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:post-edit", args=[self.post.pk]))
        self.assertEqual(response.status_code, 403)

    def test_editor_with_change_any_post_can_edit_others_post(self):
        editor = make_user("editor@example.com", "editor2")
        grant_perms(editor, "view_post", "change_post", "change_any_post")
        self.client.login(username="editor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:post-edit", args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_edit_any_post(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:post-edit", args=[self.post.pk]))
        self.assertEqual(response.status_code, 200)
