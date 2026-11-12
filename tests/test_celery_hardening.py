import datetime

from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase
from django.utils import timezone

from apps.blog.tasks import publish_scheduled_posts
from apps.core.models import ActivityLog, NotFoundLog
from apps.core.services import prune_activity_logs, prune_not_found_logs
from apps.core.tasks import cleanup_old_data

from .helpers import make_user


class RetryPolicyTests(TestCase):
    """These don't execute a retry (that would require actually raising a
    transient DatabaseError mid-task) — they confirm the *policy* is wired
    up as intended: transient failures retry with backoff, everything else
    fails once. See test_blog_celery.py for functional idempotency tests.
    """

    def test_publish_scheduled_posts_retries_only_on_database_error(self):
        self.assertEqual(publish_scheduled_posts.autoretry_for, (DatabaseError,))

    def test_publish_scheduled_posts_has_a_retry_ceiling(self):
        self.assertEqual(publish_scheduled_posts.max_retries, 3)
        self.assertTrue(publish_scheduled_posts.retry_backoff)

    def test_cleanup_old_data_retries_only_on_database_error(self):
        self.assertEqual(cleanup_old_data.autoretry_for, (DatabaseError,))

    def test_cleanup_old_data_has_a_retry_ceiling(self):
        self.assertEqual(cleanup_old_data.max_retries, 3)
        self.assertTrue(cleanup_old_data.retry_backoff)


class CleanupOldDataTaskTests(TestCase):
    def test_prunes_stale_not_found_logs(self):
        stale = NotFoundLog.objects.create(path="/stale/", hit_count=1)
        NotFoundLog.objects.filter(pk=stale.pk).update(last_seen=timezone.now() - datetime.timedelta(days=200))
        fresh = NotFoundLog.objects.create(path="/fresh/", hit_count=1)

        result = cleanup_old_data()

        self.assertEqual(result["not_found_logs_pruned"], 1)
        self.assertFalse(NotFoundLog.objects.filter(pk=stale.pk).exists())
        self.assertTrue(NotFoundLog.objects.filter(pk=fresh.pk).exists())

    def test_is_safe_to_run_twice(self):
        stale = NotFoundLog.objects.create(path="/stale-again/", hit_count=1)
        NotFoundLog.objects.filter(pk=stale.pk).update(last_seen=timezone.now() - datetime.timedelta(days=200))

        first = cleanup_old_data()
        second = cleanup_old_data()

        self.assertEqual(first["not_found_logs_pruned"], 1)
        self.assertEqual(second["not_found_logs_pruned"], 0)

    def test_recently_seen_entry_with_old_first_seen_survives(self):
        old_but_active = NotFoundLog.objects.create(path="/still-happening/", hit_count=50)
        # last_seen stays "now" (auto_now) — only an old *last_seen* should prune it.

        cleanup_old_data()

        self.assertTrue(NotFoundLog.objects.filter(pk=old_but_active.pk).exists())


class PruneNotFoundLogsServiceTests(TestCase):
    def test_custom_retention_window(self):
        entry = NotFoundLog.objects.create(path="/thirty-one-days/", hit_count=1)
        NotFoundLog.objects.filter(pk=entry.pk).update(last_seen=timezone.now() - datetime.timedelta(days=31))

        deleted = prune_not_found_logs(older_than_days=30)

        self.assertEqual(deleted, 1)


class PruneActivityLogsServiceTests(TestCase):
    def setUp(self):
        self.user = make_user("author@example.com", "author")

    def test_deletes_only_entries_older_than_cutoff(self):
        old_log = ActivityLog.objects.create(actor=self.user, action="post_created")
        ActivityLog.objects.filter(pk=old_log.pk).update(created_at=timezone.now() - datetime.timedelta(days=800))
        recent_log = ActivityLog.objects.create(actor=self.user, action="post_updated")

        deleted = prune_activity_logs(older_than_days=730)

        self.assertEqual(deleted, 1)
        self.assertFalse(ActivityLog.objects.filter(pk=old_log.pk).exists())
        self.assertTrue(ActivityLog.objects.filter(pk=recent_log.pk).exists())


class PruneActivityLogsCommandTests(TestCase):
    def test_refuses_a_suspiciously_short_retention_window(self):
        with self.assertRaises(Exception):
            call_command("prune_activity_logs", "--older-than-days", "5", "--yes")

    def test_runs_with_yes_flag_and_no_prompt(self):
        user = make_user("author@example.com", "author")
        old_log = ActivityLog.objects.create(actor=user, action="post_created")
        ActivityLog.objects.filter(pk=old_log.pk).update(created_at=timezone.now() - datetime.timedelta(days=800))

        call_command("prune_activity_logs", "--older-than-days", "730", "--yes")

        self.assertFalse(ActivityLog.objects.filter(pk=old_log.pk).exists())


class CleanupOldDataManagementCommandTests(TestCase):
    def test_command_runs_and_reports_count(self):
        from io import StringIO

        stale = NotFoundLog.objects.create(path="/cmd-stale/", hit_count=1)
        NotFoundLog.objects.filter(pk=stale.pk).update(last_seen=timezone.now() - datetime.timedelta(days=200))

        out = StringIO()
        call_command("cleanup_old_data", stdout=out)

        self.assertIn("Pruned 1", out.getvalue())
        self.assertFalse(NotFoundLog.objects.filter(pk=stale.pk).exists())
