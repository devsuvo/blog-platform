import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR
from apps.blog.models import Post, PostStatus

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class DraftAndPublishTests(TestCase):
    def setUp(self):
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "view_post", "change_post", "publish_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        self.post = make_post(self.author, title="Draft post", slug="draft-post")

    def test_new_post_saves_as_draft(self):
        self.assertEqual(self.post.status, PostStatus.DRAFT)

    def test_publish_sets_status_and_timestamp(self):
        response = self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.PUBLISHED)
        self.assertIsNotNone(self.post.published_at)

    def test_republish_does_not_change_original_published_at(self):
        self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))
        self.post.refresh_from_db()
        first_published_at = self.post.published_at

        self.client.post(reverse("dashboard:post-archive", args=[self.post.pk]))
        self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))
        self.post.refresh_from_db()

        self.assertEqual(self.post.published_at, first_published_at)

    def test_schedule_sets_scheduled_status(self):
        future = (timezone.now() + datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("dashboard:post-schedule", args=[self.post.pk]), {"scheduled_at": future})
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.SCHEDULED)
        self.assertIsNotNone(self.post.scheduled_at)

    def test_past_schedule_is_rejected(self):
        past = (timezone.now() - datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("dashboard:post-schedule", args=[self.post.pk]), {"scheduled_at": past})
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.DRAFT)

    def test_archive_then_restore_returns_to_draft(self):
        self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))
        self.client.post(reverse("dashboard:post-archive", args=[self.post.pk]))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.ARCHIVED)

        self.client.post(reverse("dashboard:post-restore", args=[self.post.pk]))
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.DRAFT)


class UnauthorizedPublishingTests(TestCase):
    def test_user_without_publish_permission_cannot_publish(self):
        author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(author, "add_post", "view_post", "change_post")  # no publish_post
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        post = make_post(author, title="Draft", slug="draft")

        response = self.client.post(reverse("dashboard:post-publish", args=[post.pk]))

        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.DRAFT)

    def test_cannot_publish_someone_elses_post_without_broad_permission(self):
        owner = make_user("owner@example.com", "owner", role=AUTHOR)
        other = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(other, "add_post", "view_post", "change_post", "publish_post")
        post = make_post(owner, title="Owner post", slug="owner-post")

        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-publish", args=[post.pk]))

        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.DRAFT)
