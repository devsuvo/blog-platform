from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR
from apps.core.models import ActivityLog

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class ExportPostsCSVTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "view_post")
        self.post = make_post(self.author, title="Exportable Post", slug="exportable-post")

    def test_requires_view_post_permission(self):
        make_user("nobody@example.com", "nobody")
        self.client.login(username="nobody@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:export-posts-csv"))
        self.assertEqual(response.status_code, 403)

    def test_export_returns_csv_with_post_data(self):
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:export-posts-csv"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        self.assertIn("Exportable Post", content)
        self.assertIn("exportable-post", content)

    def test_export_never_includes_post_content_body(self):
        make_post(self.author, title="Secretive", slug="secretive-post", content="<p>super secret internal text</p>")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:export-posts-csv"))

        self.assertNotIn("super secret internal text", response.content.decode())

    def test_author_only_exports_their_own_posts(self):
        other = make_user("other@example.com", "other", role=AUTHOR)
        make_post(other, title="Someone Elses Export Target", slug="someone-elses-export-target")

        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:export-posts-csv"))

        self.assertNotIn("Someone Elses Export Target", response.content.decode())

    def test_trashed_posts_excluded_from_export(self):
        self.post.deleted_at = timezone.now()
        self.post.save(update_fields=["deleted_at"])

        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:export-posts-csv"))

        self.assertNotIn("Exportable Post", response.content.decode())

    def test_export_is_logged(self):
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        self.client.get(reverse("dashboard:export-posts-csv"))
        self.assertTrue(ActivityLog.objects.filter(action="posts_exported").exists())


class ExportUsersCSVTests(TestCase):
    def test_requires_view_user_permission(self):
        make_user("nobody@example.com", "nobody")
        self.client.login(username="nobody@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:export-users-csv"))
        self.assertEqual(response.status_code, 403)

    def test_export_returns_csv_with_user_data_but_no_password(self):
        user = make_user("staffer@example.com", "staffer")
        grant_perms(user, "view_user", app_label="accounts")
        self.client.login(username="staffer@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:export-users-csv"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("staffer@example.com", content)
        self.assertNotIn(DEFAULT_PASSWORD, content)
        self.assertNotIn("password", content.lower())

    def test_export_is_logged(self):
        user = make_user("staffer@example.com", "staffer")
        grant_perms(user, "view_user", app_label="accounts")
        self.client.login(username="staffer@example.com", password=DEFAULT_PASSWORD)

        self.client.get(reverse("dashboard:export-users-csv"))

        self.assertTrue(ActivityLog.objects.filter(action="users_exported").exists())
