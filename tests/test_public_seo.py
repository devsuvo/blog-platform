import datetime
import json

from django.utils import timezone

from apps.blog.models import Category
from apps.public.seo import safe_json_ld

from .base import CacheClearingTestCase as TestCase
from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", "published")
    return make_post(author, **extra)


class PostSEOTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_title_falls_back_to_post_title_when_no_meta_title(self):
        post = published_post(self.author, title="My Great Post", slug="my-great-post")
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, "<title>My Great Post")

    def test_meta_title_overrides_post_title(self):
        post = published_post(
            self.author, title="My Great Post", slug="my-great-post-2", meta_title="Custom SEO Title",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, "<title>Custom SEO Title")

    def test_description_falls_back_to_excerpt(self):
        post = published_post(
            self.author, title="Post", slug="post-excerpt-fallback", excerpt="The excerpt text.",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'content="The excerpt text."')

    def test_meta_description_overrides_excerpt(self):
        post = published_post(
            self.author, title="Post", slug="post-meta-desc", excerpt="The excerpt.",
            meta_description="The meta description.",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'content="The meta description."')

    def test_canonical_uses_explicit_canonical_url_when_set(self):
        post = published_post(
            self.author, title="Post", slug="post-canonical", canonical_url="https://external.example.com/original/",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'href="https://external.example.com/original/"')

    def test_canonical_defaults_to_self_url(self):
        post = published_post(self.author, title="Post", slug="post-self-canonical")
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, f'href="http://testserver{post.get_absolute_url()}"')

    def test_robots_index_follow_by_default(self):
        post = published_post(self.author, title="Post", slug="post-robots-default")
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'content="index, follow"')

    def test_robots_respects_noindex_flag(self):
        post = published_post(self.author, title="Post", slug="post-noindex", robots_index=False)
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'content="noindex, follow"')

    def test_robots_respects_nofollow_flag(self):
        post = published_post(self.author, title="Post", slug="post-nofollow", robots_follow=False)
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'content="index, nofollow"')

    def test_og_type_is_article(self):
        post = published_post(self.author, title="Post", slug="post-og-type")
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'property="og:type" content="article"')

    def test_twitter_card_present(self):
        post = published_post(self.author, title="Post", slug="post-twitter")
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, 'name="twitter:card"')

    def test_no_og_image_tag_is_ever_rendered(self):
        post = published_post(self.author, title="Post", slug="post-no-og-image")
        response = self.client.get(post.get_absolute_url())
        self.assertNotContains(response, "og:image")

    def test_article_json_ld_is_valid_and_safe(self):
        post = published_post(self.author, title="JSON-LD Post <script>", slug="json-ld-post")
        response = self.client.get(post.get_absolute_url())
        content = response.content.decode()

        start = content.index('<script type="application/ld+json">')
        end = content.index("</script>", start)
        raw = content[start:end].split(">", 1)[1]
        data = json.loads(raw.replace("<\\/", "</"))

        self.assertEqual(data["@type"], "BlogPosting")
        self.assertIn("headline", data)
        self.assertIn("datePublished", data)

    def test_json_ld_escapes_closing_script_tags(self):
        malicious = {"headline": "</script><script>alert(1)</script>"}
        rendered = safe_json_ld(malicious)
        self.assertNotIn("</script>", rendered)


class SearchAndListingSEOTests(TestCase):
    def test_search_page_is_noindex(self):
        response = self.client.get("/search/")
        self.assertContains(response, 'content="noindex, follow"')

    def test_homepage_is_indexable(self):
        response = self.client.get("/")
        self.assertContains(response, 'content="index, follow"')

    def test_category_page_is_indexable(self):
        author = make_user("author@example.com", "author")
        category = Category.objects.create(name="Python", slug="python")
        published_post(author, title="In Category", slug="in-category", category=category)

        response = self.client.get("/category/python/")

        self.assertContains(response, 'content="index, follow"')

    def test_empty_category_page_is_noindex(self):
        Category.objects.create(name="Python", slug="python")
        response = self.client.get("/category/python/")
        self.assertContains(response, 'content="noindex, follow"')

    def test_paginated_page_canonicalizes_to_itself_not_page_one(self):
        author = make_user("author@example.com", "author")
        for i in range(15):
            published_post(author, title=f"Post {i}", slug=f"post-{i}")

        response = self.client.get("/blog/?page=2")

        self.assertContains(response, 'href="http://testserver/blog/?page=2"')

    def test_admin_panel_is_noindex(self):
        response = self.client.get("/admin/")
        # redirected to login, which should also be noindex; follow it
        response = self.client.get("/accounts/login/")
        self.assertContains(response, 'content="noindex, nofollow"')
