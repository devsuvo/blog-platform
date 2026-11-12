import datetime

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.blog.models import Category, PostStatus, Tag

from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class NoQueryScalingTests(TestCase):
    """The number of queries a listing page runs must not grow with the
    number of posts on it — that's the N+1 signature this guards against.
    """

    def setUp(self):
        self.author = make_user("author@example.com", "author")
        self.category = Category.objects.create(name="Python", slug="python")
        self.tag = Tag.objects.create(name="Django", slug="django")

    def _query_count(self, path):
        cache.clear()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_homepage_query_count_is_flat(self):
        for i in range(3):
            post = published_post(self.author, title=f"Post {i}", slug=f"post-{i}", category=self.category)
            post.tags.add(self.tag)
        small_count = self._query_count("/")

        for i in range(3, 20):
            post = published_post(self.author, title=f"Post {i}", slug=f"post-{i}", category=self.category)
            post.tags.add(self.tag)
        large_count = self._query_count("/")

        self.assertLessEqual(large_count, small_count)

    def test_blog_list_query_count_is_flat(self):
        for i in range(3):
            published_post(self.author, title=f"Post {i}", slug=f"post-{i}")
        small_count = self._query_count("/blog/")

        for i in range(3, 20):
            published_post(self.author, title=f"Post {i}", slug=f"post-{i}")
        large_count = self._query_count("/blog/")

        self.assertLessEqual(large_count, small_count)

    def test_category_page_query_count_is_flat(self):
        for i in range(3):
            published_post(self.author, title=f"Post {i}", slug=f"post-{i}", category=self.category)
        small_count = self._query_count("/category/python/")

        for i in range(3, 20):
            published_post(self.author, title=f"Post {i}", slug=f"post-{i}", category=self.category)
        large_count = self._query_count("/category/python/")

        self.assertLessEqual(large_count, small_count)


class SitemapQueryScalingTests(TestCase):
    def _query_count(self, path):
        cache.clear()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def test_sitemap_posts_section_query_count_is_flat(self):
        author = make_user("author@example.com", "author")
        for i in range(3):
            published_post(author, title=f"Post {i}", slug=f"sitemap-perf-{i}")
        small_count = self._query_count("/sitemap-posts.xml")

        for i in range(3, 20):
            published_post(author, title=f"Post {i}", slug=f"sitemap-perf-{i}")
        large_count = self._query_count("/sitemap-posts.xml")

        self.assertLessEqual(large_count, small_count)

    def test_search_query_count_is_flat(self):
        author = make_user("author@example.com", "author")
        for i in range(3):
            published_post(author, title=f"Findable {i}", slug=f"search-perf-{i}")
        small_count = self._query_count("/search/?q=Findable")

        for i in range(3, 20):
            published_post(author, title=f"Findable {i}", slug=f"search-perf-{i}")
        large_count = self._query_count("/search/?q=Findable")

        self.assertLessEqual(large_count, small_count)


class ListingCacheTests(TestCase):
    """Step 6: category/tag/author listing pages cache the ordered list of
    post PKs (not the rendered page), paginate that list in Python, and
    hydrate only the current page's rows from the database.
    """

    def setUp(self):
        self.author = make_user("author@example.com", "author")
        self.category = Category.objects.create(name="Python", slug="python")
        self.tag = Tag.objects.create(name="Django", slug="django")
        cache.clear()

    def test_category_post_ids_are_cached_after_first_request(self):
        from apps.blog.services import category_posts_cache_key

        published_post(self.author, title="In Category", slug="in-category", category=self.category)

        self.client.get(self.category.get_absolute_url())

        self.assertIsNotNone(cache.get(category_posts_cache_key(self.category.slug)))

    def test_category_second_request_runs_fewer_queries(self):
        for i in range(5):
            published_post(self.author, title=f"Post {i}", slug=f"cat-cache-{i}", category=self.category)

        with CaptureQueriesContext(connection) as first:
            self.client.get(self.category.get_absolute_url())
        with CaptureQueriesContext(connection) as second:
            self.client.get(self.category.get_absolute_url())

        self.assertLess(len(second.captured_queries), len(first.captured_queries))

    def test_invalidating_category_cache_picks_up_a_new_post(self):
        from apps.blog.services import get_category_post_ids, invalidate_category_caches

        first_ids = get_category_post_ids(self.category)
        self.assertEqual(first_ids, [])

        post = published_post(self.author, title="Just Added", slug="just-added", category=self.category)
        invalidate_category_caches(self.category)

        second_ids = get_category_post_ids(self.category)
        self.assertEqual(second_ids, [post.pk])

    def test_tag_post_ids_are_cached_and_invalidated(self):
        from apps.blog.services import get_tag_post_ids, invalidate_tag_caches

        self.assertEqual(get_tag_post_ids(self.tag), [])

        post = published_post(self.author, title="Tagged", slug="cache-tagged")
        post.tags.add(self.tag)
        invalidate_tag_caches(self.tag)

        self.assertEqual(get_tag_post_ids(self.tag), [post.pk])

    def test_author_post_ids_are_cached_and_invalidated(self):
        from apps.blog.services import get_author_post_ids, invalidate_post_caches

        self.assertEqual(get_author_post_ids(self.author), [])

        post = published_post(self.author, title="By Author", slug="cache-by-author")
        invalidate_post_caches(post)

        self.assertEqual(get_author_post_ids(self.author), [post.pk])

    def test_category_pagination_still_correct_when_served_from_cache(self):
        for i in range(15):
            published_post(self.author, title=f"Post {i}", slug=f"cat-page-{i}", category=self.category)

        self.client.get(self.category.get_absolute_url())  # warm the cache
        response = self.client.get(self.category.get_absolute_url() + "?page=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 3)  # 15 posts, page size 12


class CacheUsageTests(TestCase):
    def setUp(self):
        self.author = make_user("author@example.com", "author")
        cache.clear()

    def test_homepage_second_hit_uses_cache_and_runs_fewer_queries(self):
        for i in range(5):
            published_post(self.author, title=f"Post {i}", slug=f"post-{i}")

        with CaptureQueriesContext(connection) as first:
            self.client.get("/")
        with CaptureQueriesContext(connection) as second:
            self.client.get("/")

        self.assertLess(len(second.captured_queries), len(first.captured_queries))

    def test_latest_posts_are_actually_cached(self):
        from apps.blog.services import get_latest_posts, latest_posts_cache_key

        published_post(self.author, title="Cached Post", slug="cached-post")
        get_latest_posts()

        self.assertIsNotNone(cache.get(latest_posts_cache_key()))

    def test_publishing_a_post_invalidates_latest_posts_cache(self):
        from apps.blog.services import get_latest_posts, invalidate_post_caches, latest_posts_cache_key

        post = published_post(self.author, title="Original", slug="original")
        get_latest_posts()
        self.assertIsNotNone(cache.get(latest_posts_cache_key()))

        invalidate_post_caches(post)

        self.assertIsNone(cache.get(latest_posts_cache_key()))
