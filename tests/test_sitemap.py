import datetime

from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.blog.models import Category, PostStatus, Tag

from .base import CacheClearingTestCase as TestCase
from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class SitemapIndexTests(TestCase):
    def test_sitemap_index_is_xml(self):
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("xml", response["Content-Type"])

    def test_sitemap_index_references_every_section(self):
        response = self.client.get("/sitemap.xml")
        content = response.content.decode()
        for section in ("posts", "categories", "tags", "authors", "static"):
            self.assertIn(f"sitemap-{section}.xml", content)

    def test_unknown_section_404s(self):
        response = self.client.get("/sitemap-bogus.xml")
        self.assertEqual(response.status_code, 404)


class SitemapPostSectionTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_published_post_appears_in_sitemap(self):
        post = published_post(self.author, title="Visible", slug="sitemap-visible")
        response = self.client.get("/sitemap-posts.xml")
        self.assertContains(response, post.get_absolute_url())

    def test_draft_post_excluded_from_sitemap(self):
        post = make_post(self.author, title="Draft", slug="sitemap-draft", status=PostStatus.DRAFT)
        response = self.client.get("/sitemap-posts.xml")
        self.assertNotContains(response, post.get_absolute_url())

    def test_scheduled_post_excluded_from_sitemap(self):
        post = make_post(
            self.author, title="Scheduled", slug="sitemap-scheduled", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() + datetime.timedelta(days=1),
        )
        response = self.client.get("/sitemap-posts.xml")
        self.assertNotContains(response, post.get_absolute_url())

    def test_archived_post_excluded_from_sitemap(self):
        post = make_post(self.author, title="Archived", slug="sitemap-archived", status=PostStatus.ARCHIVED)
        response = self.client.get("/sitemap-posts.xml")
        self.assertNotContains(response, post.get_absolute_url())


class SitemapCategoryTagAuthorSectionTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_category_with_published_post_appears(self):
        category = Category.objects.create(name="Python", slug="python")
        published_post(self.author, title="P", slug="cat-sitemap-post", category=category)
        response = self.client.get("/sitemap-categories.xml")
        self.assertContains(response, category.get_absolute_url())

    def test_empty_category_excluded(self):
        category = Category.objects.create(name="Empty", slug="empty-cat")
        response = self.client.get("/sitemap-categories.xml")
        self.assertNotContains(response, category.get_absolute_url())

    def test_tag_with_published_post_appears(self):
        tag = Tag.objects.create(name="Django", slug="django")
        post = published_post(self.author, title="Tagged", slug="tag-sitemap-post")
        post.tags.add(tag)
        response = self.client.get("/sitemap-tags.xml")
        self.assertContains(response, tag.get_absolute_url())

    def test_empty_tag_excluded(self):
        tag = Tag.objects.create(name="Unused", slug="unused-tag")
        response = self.client.get("/sitemap-tags.xml")
        self.assertNotContains(response, tag.get_absolute_url())

    def test_author_with_published_post_appears(self):
        published_post(self.author, title="A", slug="author-sitemap-post")
        response = self.client.get("/sitemap-authors.xml")
        self.assertIn(f"/author/{self.author.username}/", response.content.decode())

    def test_ghost_author_excluded(self):
        make_user("ghost@example.com", "ghost")
        response = self.client.get("/sitemap-authors.xml")
        self.assertNotIn("/author/ghost/", response.content.decode())


class SitemapStaticSectionTests(TestCase):
    def test_static_section_includes_homepage(self):
        response = self.client.get("/sitemap-static.xml")
        self.assertContains(response, "<loc>http://testserver/</loc>")

    def test_static_section_includes_blog_list(self):
        response = self.client.get("/sitemap-static.xml")
        self.assertContains(response, "/blog/</loc>")


class SitemapCachingTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")
        cache.clear()

    def test_sitemap_section_is_cached_after_first_request(self):
        published_post(self.author, title="Cached", slug="cached-sitemap-post")

        with CaptureQueriesContext(connection) as first:
            self.client.get("/sitemap-posts.xml")
        with CaptureQueriesContext(connection) as second:
            self.client.get("/sitemap-posts.xml")

        self.assertGreater(len(first.captured_queries), 0)
        self.assertEqual(len(second.captured_queries), 0)

    def test_invalidate_post_caches_clears_every_sitemap_section(self):
        from apps.blog.services import SITEMAP_SECTIONS, invalidate_post_caches, sitemap_cache_key

        post = published_post(self.author, title="Cached", slug="invalidate-sitemap-post")
        for section in SITEMAP_SECTIONS:
            cache.set(sitemap_cache_key(section), b"<stale/>", 300)

        invalidate_post_caches(post)

        for section in SITEMAP_SECTIONS:
            self.assertIsNone(cache.get(sitemap_cache_key(section)))

    def test_publishing_a_post_through_dashboard_invalidates_and_reappears_in_sitemap(self):
        from django.urls import reverse

        from apps.accounts.roles import AUTHOR

        from .helpers import DEFAULT_PASSWORD, grant_perms

        self.client.get("/sitemap-posts.xml")  # warm the cache while empty

        writer = make_user("writer@example.com", "writer", role=AUTHOR)
        grant_perms(writer, "add_post", "view_post", "publish_post")
        self.client.login(username="writer@example.com", password=DEFAULT_PASSWORD)

        self.client.post(reverse("dashboard:post-create"), {
            "title": "Fresh Dashboard Post", "slug": "", "excerpt": "", "content": "<p>Body</p>",
            "category": "", "tags": [],
        })
        post = writer.posts.get(slug="fresh-dashboard-post")
        self.client.post(reverse("dashboard:post-publish", args=[post.pk]))

        response = self.client.get("/sitemap-posts.xml")
        self.assertContains(response, "fresh-dashboard-post")
