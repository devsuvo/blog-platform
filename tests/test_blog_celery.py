import datetime

from django.test import TestCase
from django.utils import timezone

from apps.blog.models import PostStatus
from apps.blog.tasks import publish_scheduled_posts
from apps.core.models import ActivityLog

from .helpers import make_post, make_user


class ScheduledPublishingTaskTests(TestCase):
    def setUp(self):
        self.author = make_user("author@example.com", "author")

    def test_due_scheduled_post_gets_published(self):
        post = make_post(
            self.author, title="Due", slug="due", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() - datetime.timedelta(minutes=1),
        )

        published_count = publish_scheduled_posts()

        post.refresh_from_db()
        self.assertEqual(published_count, 1)
        self.assertEqual(post.status, PostStatus.PUBLISHED)
        self.assertIsNotNone(post.published_at)
        self.assertTrue(ActivityLog.objects.filter(action="post_published", target_object_id=str(post.pk)).exists())

    def test_future_scheduled_post_is_not_published(self):
        post = make_post(
            self.author, title="Future", slug="future", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() + datetime.timedelta(hours=1),
        )

        published_count = publish_scheduled_posts()

        post.refresh_from_db()
        self.assertEqual(published_count, 0)
        self.assertEqual(post.status, PostStatus.SCHEDULED)

    def test_running_task_twice_is_idempotent(self):
        post = make_post(
            self.author, title="Due", slug="due", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() - datetime.timedelta(minutes=1),
        )

        first_count = publish_scheduled_posts()
        post.refresh_from_db()
        first_published_at = post.published_at

        second_count = publish_scheduled_posts()
        post.refresh_from_db()

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 0)
        self.assertEqual(post.published_at, first_published_at)
        self.assertEqual(
            ActivityLog.objects.filter(action="post_published", target_object_id=str(post.pk)).count(), 1
        )
