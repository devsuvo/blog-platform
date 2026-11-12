import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR, EDITOR
from apps.blog.models import Category, Post, PostStatus

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class BulkActionAccessTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "view_post")
        self.post = make_post(self.author, title="Bulk Target", slug="bulk-target")

    def test_requires_login(self):
        response = self.client.post(reverse("dashboard:post-bulk-action"), {
            "action": "archive", "post_ids": str(self.post.pk),
        })
        self.assertEqual(response.status_code, 302)

    def test_requires_change_post_permission(self):
        make_user("nobody@example.com", "nobody")
        self.client.login(username="nobody@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-bulk-action"), {
            "action": "archive", "post_ids": str(self.post.pk),
        })
        self.assertEqual(response.status_code, 403)


class BulkActionBehaviorTests(TestCase):
    def setUp(self):
        super().setUp()
        self.editor = make_user("editor@example.com", "editor", role=EDITOR)
        grant_perms(
            self.editor, "add_post", "change_post", "change_any_post",
            "delete_post", "delete_any_post", "publish_post", "view_post",
        )
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        self.client.login(username="editor@example.com", password=DEFAULT_PASSWORD)

    def test_bulk_publish(self):
        posts = [make_post(self.author, title=f"P{i}", slug=f"bulk-pub-{i}") for i in range(3)]
        ids = ",".join(str(p.pk) for p in posts)

        response = self.client.post(reverse("dashboard:post-bulk-action"), {"action": "publish", "post_ids": ids})

        self.assertEqual(response.status_code, 302)
        for post in posts:
            post.refresh_from_db()
            self.assertEqual(post.status, PostStatus.PUBLISHED)
            self.assertIsNotNone(post.published_at)

    def test_bulk_unpublish(self):
        posts = [published_post(self.author, title=f"P{i}", slug=f"bulk-unpub-{i}") for i in range(2)]
        ids = ",".join(str(p.pk) for p in posts)

        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "unpublish", "post_ids": ids})

        for post in posts:
            post.refresh_from_db()
            self.assertEqual(post.status, PostStatus.DRAFT)

    def test_bulk_archive(self):
        posts = [make_post(self.author, title=f"P{i}", slug=f"bulk-arch-{i}") for i in range(2)]
        ids = ",".join(str(p.pk) for p in posts)

        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "archive", "post_ids": ids})

        for post in posts:
            post.refresh_from_db()
            self.assertEqual(post.status, PostStatus.ARCHIVED)

    def test_bulk_trash(self):
        posts = [make_post(self.author, title=f"P{i}", slug=f"bulk-trash-{i}") for i in range(2)]
        ids = ",".join(str(p.pk) for p in posts)

        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "trash", "post_ids": ids})

        for post in posts:
            post.refresh_from_db()
            self.assertIsNotNone(post.deleted_at)

    def test_bulk_change_category(self):
        category = Category.objects.create(name="Tech", slug="tech")
        posts = [make_post(self.author, title=f"P{i}", slug=f"bulk-cat-{i}") for i in range(2)]
        ids = ",".join(str(p.pk) for p in posts)

        self.client.post(reverse("dashboard:post-bulk-action"), {
            "action": "change_category", "post_ids": ids, "category": category.pk,
        })

        for post in posts:
            post.refresh_from_db()
            self.assertEqual(post.category_id, category.pk)

    def test_change_category_without_a_category_selected_is_rejected(self):
        posts = [make_post(self.author, title="P", slug="bulk-cat-none")]
        response = self.client.post(reverse("dashboard:post-bulk-action"), {
            "action": "change_category", "post_ids": str(posts[0].pk),
        })
        self.assertEqual(response.status_code, 302)
        posts[0].refresh_from_db()
        self.assertIsNone(posts[0].category)

    def test_empty_selection_is_rejected(self):
        response = self.client.post(reverse("dashboard:post-bulk-action"), {"action": "archive", "post_ids": ""})
        self.assertEqual(response.status_code, 302)

    def test_invalid_action_is_rejected(self):
        post = make_post(self.author, title="P", slug="bulk-invalid-action")
        response = self.client.post(reverse("dashboard:post-bulk-action"), {
            "action": "launch_missiles", "post_ids": str(post.pk),
        })
        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.DRAFT)


class BulkActionObjectLevelSecurityTests(TestCase):
    """A bulk request naming someone else's post must skip that post, not
    silently act on it just because it rode along with authorized ones.
    """

    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "delete_post", "publish_post", "view_post")
        self.other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(self.other, "add_post", "change_post", "delete_post", "publish_post", "view_post")
        self.own_post = make_post(self.author, title="Mine", slug="bulk-sec-mine")
        self.others_post = make_post(self.other, title="Theirs", slug="bulk-sec-theirs")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_cannot_bulk_archive_someone_elses_post_by_including_its_id(self):
        ids = f"{self.own_post.pk},{self.others_post.pk}"

        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "archive", "post_ids": ids})

        self.own_post.refresh_from_db()
        self.others_post.refresh_from_db()
        self.assertEqual(self.own_post.status, PostStatus.ARCHIVED)
        self.assertEqual(self.others_post.status, PostStatus.DRAFT)

    def test_cannot_bulk_trash_someone_elses_post_via_queryset_scoping(self):
        # _post_queryset_for() scopes to the caller's own posts unless they
        # hold change_any_post — the other author's post is filtered out
        # before the bulk loop ever sees it, not just skipped inside it.
        ids = str(self.others_post.pk)

        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "trash", "post_ids": ids})

        self.others_post.refresh_from_db()
        self.assertIsNone(self.others_post.deleted_at)


class BulkPublishPermissionTests(TestCase):
    """Publish specifically requires blog.publish_post — change_post alone
    (which the other bulk actions accept) must not be enough.
    """

    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "change_any_post", "view_post")  # no publish_post
        self.other_author = make_user("writer@example.com", "writer", role=AUTHOR)
        self.post = make_post(self.other_author, title="Needs Publish Perm", slug="needs-publish-perm")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_bulk_publish_without_publish_permission_is_skipped(self):
        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "publish", "post_ids": str(self.post.pk)})

        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.DRAFT)

    def test_bulk_archive_with_only_change_permission_still_works(self):
        self.client.post(reverse("dashboard:post-bulk-action"), {"action": "archive", "post_ids": str(self.post.pk)})

        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.ARCHIVED)
