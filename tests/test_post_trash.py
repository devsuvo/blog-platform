import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR, SUPER_ADMIN
from apps.blog.models import Post, PostStatus

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class SoftDeleteTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "delete_post", "view_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_delete_moves_to_trash_not_hard_delete(self):
        post = make_post(self.author, title="Trash Me", slug="trash-me", status=PostStatus.DRAFT)

        response = self.client.post(reverse("dashboard:post-delete", args=[post.pk]))

        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertIsNotNone(post.deleted_at)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())

    def test_trashed_post_disappears_from_public_site(self):
        post = published_post(self.author, title="Was Public", slug="was-public")

        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))

        response = self.client.get(post.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_trashed_post_disappears_from_admin_post_list(self):
        post = make_post(self.author, title="Hidden From List", slug="hidden-from-list")
        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))
        self.client.get(reverse("dashboard:post-list"))  # consume the "moved to trash" flash message first

        response = self.client.get(reverse("dashboard:post-list"))

        self.assertNotContains(response, "Hidden From List")

    def test_trashed_post_appears_in_trash_list(self):
        post = make_post(self.author, title="In Trash List", slug="in-trash-list")
        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))

        response = self.client.get(reverse("dashboard:post-trash-list"))

        self.assertContains(response, "In Trash List")

    def test_cannot_edit_a_trashed_post_directly(self):
        post = make_post(self.author, title="Locked", slug="locked-post")
        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))

        response = self.client.get(reverse("dashboard:post-edit", args=[post.pk]))

        self.assertRedirects(response, reverse("dashboard:post-trash-list"))

    def test_restore_from_trash(self):
        post = make_post(self.author, title="Restore Me", slug="restore-me")
        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))

        response = self.client.post(reverse("dashboard:post-trash-restore", args=[post.pk]))

        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertIsNone(post.deleted_at)

    def test_deleting_an_already_trashed_post_is_a_no_op(self):
        post = make_post(self.author, title="Already Trashed", slug="already-trashed")
        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))
        first_deleted_at = Post.objects.get(pk=post.pk).deleted_at

        self.client.post(reverse("dashboard:post-delete", args=[post.pk]))

        post.refresh_from_db()
        self.assertEqual(post.deleted_at, first_deleted_at)


class TrashObjectLevelSecurityTests(TestCase):
    """Trash/restore must respect the same ownership rules as delete —
    changing the URL's pk must never let one author touch another's post.
    """

    def setUp(self):
        super().setUp()
        self.owner = make_user("owner@example.com", "owner", role=AUTHOR)
        grant_perms(self.owner, "add_post", "delete_post", "view_post")
        self.other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(self.other, "add_post", "delete_post", "view_post")
        self.post = make_post(self.owner, title="Owners Post", slug="owners-post")

    def test_other_user_cannot_trash_someone_elses_post(self):
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-delete", args=[self.post.pk]))
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_restore_someone_elses_trashed_post(self):
        self.post.deleted_at = timezone.now()
        self.post.save(update_fields=["deleted_at"])

        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-trash-restore", args=[self.post.pk]))

        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertIsNotNone(self.post.deleted_at)

    def test_trash_list_only_shows_own_posts_for_an_author(self):
        self.post.deleted_at = timezone.now()
        self.post.save(update_fields=["deleted_at"])
        other_post = make_post(self.other, title="Other Persons Trashed Post", slug="others-trashed-post")
        other_post.deleted_at = timezone.now()
        other_post.save(update_fields=["deleted_at"])

        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:post-trash-list"))

        self.assertContains(response, "Other Persons Trashed Post")
        self.assertNotContains(response, "Owners Post")


class PermanentDeleteTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "delete_post", "view_post")
        self.post = make_post(self.author, title="To Be Purged", slug="to-be-purged")
        self.post.deleted_at = timezone.now()
        self.post.save(update_fields=["deleted_at"])

    def test_non_superuser_cannot_permanently_delete(self):
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-permanent-delete", args=[self.post.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_superuser_can_permanently_delete_a_trashed_post(self):
        make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-permanent-delete", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_cannot_permanently_delete_a_post_that_is_not_trashed(self):
        self.post.deleted_at = None
        self.post.save(update_fields=["deleted_at"])
        make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-permanent-delete", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())
