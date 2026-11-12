import datetime

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR, SUPER_ADMIN
from apps.blog.models import Category, PostStatus, Tag

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class DashboardStatsContentTests(TestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

    def test_dashboard_shows_real_post_counts(self):
        published_post(self.owner, title="Pub", slug="dash-pub")
        make_post(self.owner, title="Draft", slug="dash-draft")

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.context["stats"]["published_posts"], 1)
        self.assertEqual(response.context["stats"]["draft_posts"], 1)

    def test_dashboard_shows_category_and_tag_counts(self):
        Category.objects.create(name="Tech", slug="tech")
        Tag.objects.create(name="Django", slug="django")

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.context["stats"]["total_categories"], 1)
        self.assertEqual(response.context["stats"]["total_tags"], 1)

    def test_dashboard_counts_authors_as_users_with_at_least_one_post(self):
        make_user("ghost@example.com", "ghost")  # no posts — shouldn't count as an author
        published_post(self.owner, title="Post", slug="dash-authors")

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.context["stats"]["total_authors"], 1)

    def test_trashed_posts_excluded_from_dashboard_counts(self):
        post = make_post(self.owner, title="Trashed", slug="dash-trashed")
        post.deleted_at = timezone.now()
        post.save(update_fields=["deleted_at"])

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.context["stats"]["total_posts"], 0)

    def test_recent_posts_and_top_posts_present(self):
        published_post(self.owner, title="Recent", slug="dash-recent", views_count=50)

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(len(response.context["stats"]["recent_posts"]), 1)
        self.assertEqual(len(response.context["stats"]["top_posts"]), 1)


class DashboardCacheTests(TestCase):
    def setUp(self):
        super().setUp()
        self.owner = make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        cache.clear()

    def test_stats_are_cached(self):
        from apps.dashboard.services import dashboard_stats_cache_key

        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)
        self.client.get(reverse("dashboard:index"))

        self.assertIsNotNone(cache.get(dashboard_stats_cache_key(self.owner)))

    def test_publishing_a_post_invalidates_dashboard_cache(self):
        from apps.dashboard.services import dashboard_stats_cache_key, get_dashboard_stats

        get_dashboard_stats(self.owner)
        self.assertIsNotNone(cache.get(dashboard_stats_cache_key(self.owner)))

        post = make_post(self.owner, title="New", slug="dash-cache-invalidate")
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)
        self.client.post(reverse("dashboard:post-publish", args=[post.pk]))

        self.assertIsNone(cache.get(dashboard_stats_cache_key(self.owner)))

    def test_stats_reflect_new_post_after_cache_invalidation(self):
        from apps.dashboard.services import get_dashboard_stats, invalidate_dashboard_stats

        first = get_dashboard_stats(self.owner)
        self.assertEqual(first["total_posts"], 0)

        make_post(self.owner, title="Fresh", slug="dash-cache-fresh")
        invalidate_dashboard_stats(author=self.owner)

        second = get_dashboard_stats(self.owner)
        self.assertEqual(second["total_posts"], 1)

    def test_author_scoped_cache_is_separate_from_global(self):
        from apps.dashboard.services import dashboard_stats_cache_key

        author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(author, "view_post")

        self.assertNotEqual(dashboard_stats_cache_key(self.owner), dashboard_stats_cache_key(author))
