import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.blog.analytics import post_view_stats, prune_post_view_daily, record_post_view, top_posts
from apps.blog.models import PostStatus, PostViewDaily
from apps.core.models import SiteSetting
from apps.public.services import prune_search_query_stats, record_search_query, top_search_queries

from .base import CacheClearingTestCase as TestCase
from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class PostViewAggregationTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")
        self.post = published_post(self.author, title="Analytics Post", slug="analytics-post")

    def test_single_view_creates_a_daily_row(self):
        record_post_view(self.post)
        row = PostViewDaily.objects.get(post=self.post, date=timezone.localdate())
        self.assertEqual(row.views, 1)

    def test_multiple_views_same_day_aggregate_into_one_row(self):
        record_post_view(self.post)
        record_post_view(self.post)
        record_post_view(self.post)

        self.assertEqual(PostViewDaily.objects.filter(post=self.post).count(), 1)
        self.assertEqual(PostViewDaily.objects.get(post=self.post).views, 3)

    def test_disabled_analytics_records_nothing(self):
        settings_obj = SiteSetting.load()
        settings_obj.analytics_enabled = False
        settings_obj.save()

        record_post_view(self.post)

        self.assertFalse(PostViewDaily.objects.filter(post=self.post).exists())

    def test_real_page_view_triggers_aggregation(self):
        self.client.get(self.post.get_absolute_url())
        self.assertTrue(PostViewDaily.objects.filter(post=self.post).exists())

    def test_view_stats_breaks_down_by_window(self):
        today = timezone.localdate()
        PostViewDaily.objects.create(post=self.post, date=today, views=5)
        PostViewDaily.objects.create(post=self.post, date=today - datetime.timedelta(days=10), views=20)
        PostViewDaily.objects.create(post=self.post, date=today - datetime.timedelta(days=60), views=100)
        self.post.views_count = 125
        self.post.save(update_fields=["views_count"])

        stats = post_view_stats(self.post)

        self.assertEqual(stats["all_time"], 125)
        self.assertEqual(stats["last_7_days"], 5)
        self.assertEqual(stats["last_30_days"], 25)

    def test_top_posts_ranked_by_all_time_views(self):
        self.post.views_count = 10
        self.post.save(update_fields=["views_count"])
        popular = published_post(self.author, title="Popular", slug="popular-post", views_count=100)

        results = top_posts(limit=5)

        self.assertEqual(results[0].pk, popular.pk)

    def test_top_posts_windowed_uses_daily_aggregate(self):
        today = timezone.localdate()
        quiet_post = published_post(self.author, title="Quiet Overall", slug="quiet-overall", views_count=1000)
        PostViewDaily.objects.create(post=quiet_post, date=today - datetime.timedelta(days=90), views=1000)
        PostViewDaily.objects.create(post=self.post, date=today, views=50)

        results = top_posts(limit=5, days=7)

        self.assertEqual(results[0].pk, self.post.pk)

    def test_prune_removes_old_daily_rows_only(self):
        today = timezone.localdate()
        old_row = PostViewDaily.objects.create(post=self.post, date=today - datetime.timedelta(days=400), views=1)
        recent_row = PostViewDaily.objects.create(post=self.post, date=today, views=1)

        deleted = prune_post_view_daily(older_than_days=395)

        self.assertEqual(deleted, 1)
        self.assertFalse(PostViewDaily.objects.filter(pk=old_row.pk).exists())
        self.assertTrue(PostViewDaily.objects.filter(pk=recent_row.pk).exists())


class SearchQueryAnalyticsTests(TestCase):
    def test_recording_a_search_creates_a_stat_row(self):
        record_search_query("django tutorial")
        stat = top_search_queries()[0]
        self.assertEqual(stat.query, "django tutorial")
        self.assertEqual(stat.hit_count, 1)

    def test_repeated_search_increments_hit_count(self):
        record_search_query("python")
        record_search_query("python")
        record_search_query("PYTHON")  # normalized to lowercase — same row

        stat = top_search_queries()[0]
        self.assertEqual(stat.query, "python")
        self.assertEqual(stat.hit_count, 3)

    def test_query_is_length_capped(self):
        record_search_query("x" * 500)
        stat = top_search_queries()[0]
        self.assertLessEqual(len(stat.query), 100)

    def test_empty_query_is_not_recorded(self):
        record_search_query("   ")
        self.assertEqual(len(top_search_queries()), 0)

    def test_disabled_tracking_records_nothing(self):
        settings_obj = SiteSetting.load()
        settings_obj.track_search = False
        settings_obj.save()

        record_search_query("should not be recorded")

        self.assertEqual(len(top_search_queries()), 0)

    @override_settings(RATELIMIT_ENABLE=False)
    def test_real_search_request_records_a_query(self):
        self.client.get("/search/", {"q": "real search term"})
        stat = top_search_queries()[0]
        self.assertEqual(stat.query, "real search term")

    def test_prune_removes_only_stale_stats(self):
        from apps.public.models import SearchQueryStat

        stale = SearchQueryStat.objects.create(query="stale term")
        SearchQueryStat.objects.filter(pk=stale.pk).update(
            last_searched_at=timezone.now() - datetime.timedelta(days=200)
        )
        record_search_query("fresh term")

        deleted = prune_search_query_stats(older_than_days=180)

        self.assertEqual(deleted, 1)
        self.assertFalse(SearchQueryStat.objects.filter(pk=stale.pk).exists())
        self.assertTrue(SearchQueryStat.objects.filter(query="fresh term").exists())
