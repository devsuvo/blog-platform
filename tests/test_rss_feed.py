import datetime

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.blog.models import PostStatus
from apps.core.models import SiteSetting

from .base import CacheClearingTestCase as TestCase
from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class RSSFeedPublicationRulesTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_published_post_appears_in_feed(self):
        post = published_post(self.author, title="In Feed", slug="rss-published")
        response = self.client.get(reverse("public:feed"))
        self.assertContains(response, post.get_absolute_url())

    def test_draft_post_excluded_from_feed(self):
        make_post(self.author, title="Draft Not In Feed", slug="rss-draft", status=PostStatus.DRAFT)
        response = self.client.get(reverse("public:feed"))
        self.assertNotContains(response, "Draft Not In Feed")

    def test_scheduled_post_excluded_from_feed(self):
        make_post(
            self.author, title="Scheduled Not In Feed", slug="rss-scheduled", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() + datetime.timedelta(days=1),
        )
        response = self.client.get(reverse("public:feed"))
        self.assertNotContains(response, "Scheduled Not In Feed")

    def test_archived_post_excluded_from_feed(self):
        make_post(self.author, title="Archived Not In Feed", slug="rss-archived", status=PostStatus.ARCHIVED)
        response = self.client.get(reverse("public:feed"))
        self.assertNotContains(response, "Archived Not In Feed")

    def test_future_published_at_excluded_from_feed(self):
        make_post(
            self.author, title="Not Due Yet In Feed", slug="rss-not-due", status=PostStatus.PUBLISHED,
            published_at=timezone.now() + datetime.timedelta(hours=2),
        )
        response = self.client.get(reverse("public:feed"))
        self.assertNotContains(response, "Not Due Yet In Feed")

    def test_feed_orders_newest_first(self):
        older = published_post(
            self.author, title="Older", slug="rss-older", published_at=timezone.now() - datetime.timedelta(days=2),
        )
        newer = published_post(
            self.author, title="Newer", slug="rss-newer", published_at=timezone.now() - datetime.timedelta(hours=1),
        )
        response = self.client.get(reverse("public:feed"))
        content = response.content.decode()
        self.assertLess(content.index(newer.get_absolute_url()), content.index(older.get_absolute_url()))


class RSSFeedContentTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_item_description_falls_back_to_excerpt(self):
        published_post(
            self.author, title="Excerpt Fallback", slug="rss-excerpt", excerpt="The excerpt text.",
            meta_description="",
        )
        response = self.client.get(reverse("public:feed"))
        self.assertContains(response, "The excerpt text.")

    def test_item_description_prefers_meta_description(self):
        published_post(
            self.author, title="Meta Wins", slug="rss-meta-wins", excerpt="The excerpt.",
            meta_description="The meta description.",
        )
        response = self.client.get(reverse("public:feed"))
        self.assertContains(response, "The meta description.")

    def test_feed_link_points_to_homepage(self):
        response = self.client.get(reverse("public:feed"))
        self.assertContains(response, "<link>http://testserver/</link>")

    def test_feed_reflects_updated_site_name_without_restart(self):
        # Regression guard: the feed response is now cached (Step 6), so
        # this only stays true because SiteSetting.save() invalidates the
        # settings cache — not the RSS cache — and title()/description()
        # are still evaluated fresh on this first (uncached) request.
        settings_obj = SiteSetting.load()
        settings_obj.site_name = "Renamed Via Settings"
        settings_obj.save()

        response = self.client.get(reverse("public:feed"))

        self.assertContains(response, "Renamed Via Settings")


class RSSFeedCachingTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_feed_response_is_cached_after_first_request(self):
        from apps.blog.services import rss_feed_cache_key

        self.client.get(reverse("public:feed"))

        self.assertIsNotNone(cache.get(rss_feed_cache_key()))

    def test_publishing_a_post_invalidates_the_feed_cache(self):
        from apps.blog.services import invalidate_post_caches, rss_feed_cache_key

        self.client.get(reverse("public:feed"))
        self.assertIsNotNone(cache.get(rss_feed_cache_key()))

        post = published_post(self.author, title="Invalidation Trigger", slug="rss-invalidation")
        invalidate_post_caches(post)

        self.assertIsNone(cache.get(rss_feed_cache_key()))

    def test_new_post_appears_in_feed_after_cache_invalidation(self):
        from apps.blog.services import invalidate_post_caches

        self.client.get(reverse("public:feed"))  # warm the cache while empty

        post = published_post(self.author, title="Appears After Invalidation", slug="rss-appears-after")
        invalidate_post_caches(post)

        response = self.client.get(reverse("public:feed"))
        self.assertContains(response, "Appears After Invalidation")
