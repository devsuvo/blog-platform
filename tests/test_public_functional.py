import datetime

from django.urls import reverse
from django.utils import timezone

from apps.blog.models import Category, Post, PostStatus, Tag

from .base import CacheClearingTestCase as TestCase
from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class HomePageTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_homepage_loads(self):
        response = self.client.get(reverse("public:home"))
        self.assertEqual(response.status_code, 200)

    def test_homepage_shows_only_published_posts(self):
        published_post(self.author, title="Visible Post", slug="visible-post")
        make_post(self.author, title="Draft Post", slug="draft-post", status=PostStatus.DRAFT)
        make_post(
            self.author, title="Future Post", slug="future-post", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() + datetime.timedelta(days=1),
        )

        response = self.client.get(reverse("public:home"))

        self.assertContains(response, "Visible Post")
        self.assertNotContains(response, "Draft Post")
        self.assertNotContains(response, "Future Post")

    def test_homepage_excludes_post_published_in_the_future(self):
        # status=PUBLISHED but published_at hasn't arrived yet — must not show.
        make_post(
            self.author, title="Not Due Yet", slug="not-due-yet", status=PostStatus.PUBLISHED,
            published_at=timezone.now() + datetime.timedelta(hours=2),
        )
        response = self.client.get(reverse("public:home"))
        self.assertNotContains(response, "Not Due Yet")

    def test_homepage_handles_zero_posts_gracefully(self):
        response = self.client.get(reverse("public:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "check back soon")


class BlogListTests(TestCase):
    def test_pagination_limits_posts_per_page(self):
        author = make_user("author@example.com", "author")
        for i in range(15):
            published_post(author, title=f"Post {i}", slug=f"post-{i}")

        response = self.client.get(reverse("public:blog-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["page_obj"].object_list), 12)
        self.assertTrue(response.context["page_obj"].has_next())


class PostDetailTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")
        self.category = Category.objects.create(name="Python", slug="python")
        self.tag = Tag.objects.create(name="Django", slug="django")

    def test_published_post_is_accessible(self):
        post = published_post(self.author, title="A Real Post", slug="a-real-post", category=self.category)
        post.tags.add(self.tag)

        response = self.client.get(post.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A Real Post")

    def test_draft_post_is_not_accessible(self):
        post = make_post(self.author, title="Secret Draft", slug="secret-draft", status=PostStatus.DRAFT)
        response = self.client.get(post.get_absolute_url())
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Secret Draft", status_code=404)

    def test_scheduled_post_is_not_accessible(self):
        post = make_post(
            self.author, title="Future Secret", slug="future-secret", status=PostStatus.SCHEDULED,
            scheduled_at=timezone.now() + datetime.timedelta(days=1),
        )
        response = self.client.get(post.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_archived_post_is_not_accessible(self):
        post = make_post(self.author, title="Old News", slug="old-news", status=PostStatus.ARCHIVED)
        response = self.client.get(post.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_view_count_increments_once_per_session(self):
        post = published_post(self.author, title="Counted", slug="counted", views_count=0)

        self.client.get(post.get_absolute_url())
        self.client.get(post.get_absolute_url())
        self.client.get(post.get_absolute_url())

        post.refresh_from_db()
        self.assertEqual(post.views_count, 1)

    def test_content_renders_unescaped_as_html(self):
        post = published_post(
            self.author, title="Has Markup", slug="has-markup",
            content="<h2>Section</h2><p>Body <strong>text</strong></p>",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, "<strong>text</strong>")

    def test_toc_hidden_for_short_articles(self):
        post = published_post(
            self.author, title="Short", slug="short-article", content="<p>Just one short paragraph.</p>",
        )
        response = self.client.get(post.get_absolute_url())
        self.assertNotContains(response, "Table of Contents")

    def test_toc_shown_for_articles_with_enough_headings(self):
        content = "".join(f"<h2>Section {i}</h2><p>Text {i}</p>" for i in range(4))
        post = published_post(self.author, title="Long", slug="long-article", content=content)
        response = self.client.get(post.get_absolute_url())
        self.assertContains(response, "Table of Contents")
        self.assertContains(response, 'id="section-1"')

    def test_related_posts_exclude_current_post(self):
        post = published_post(self.author, title="Main", slug="main-post", category=self.category)
        related = published_post(self.author, title="Related", slug="related-post", category=self.category)

        response = self.client.get(post.get_absolute_url())

        related_ids = [p.pk for p in response.context["related_posts"]]
        self.assertIn(related.pk, related_ids)
        self.assertNotIn(post.pk, related_ids)

    def test_old_slug_redirects_to_new_slug(self):
        from apps.public.models import Redirect

        post = published_post(self.author, title="Renamed", slug="new-slug-name")
        Redirect.objects.create(old_path="/blog/old-slug-name/", new_path=post.get_absolute_url())

        response = self.client.get("/blog/old-slug-name/")

        self.assertRedirects(response, post.get_absolute_url(), status_code=301, target_status_code=200)


class CategoryTagAuthorTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")
        self.category = Category.objects.create(name="Python", slug="python")
        self.tag = Tag.objects.create(name="Django", slug="django")

    def test_category_page_shows_only_published_posts_in_category(self):
        published_post(self.author, title="In Category", slug="in-category", category=self.category)
        make_post(self.author, title="Draft In Category", slug="draft-in-category", category=self.category, status=PostStatus.DRAFT)
        other_category = Category.objects.create(name="Other", slug="other")
        published_post(self.author, title="Other Category", slug="other-category-post", category=other_category)

        response = self.client.get(self.category.get_absolute_url())

        self.assertContains(response, "In Category")
        self.assertNotContains(response, "Draft In Category")
        self.assertNotContains(response, "Other Category")

    def test_category_404_for_unknown_slug(self):
        response = self.client.get("/category/does-not-exist/")
        self.assertEqual(response.status_code, 404)

    def test_tag_page_shows_only_published_posts_with_tag(self):
        tagged = published_post(self.author, title="Tagged Post", slug="tagged-post")
        tagged.tags.add(self.tag)
        published_post(self.author, title="Untagged Post", slug="untagged-post")

        response = self.client.get(self.tag.get_absolute_url())

        self.assertContains(response, "Tagged Post")
        self.assertNotContains(response, "Untagged Post")

    def test_author_page_shows_only_that_authors_published_posts(self):
        other = make_user("other@example.com", "other")
        published_post(self.author, title="By Author", slug="by-author")
        published_post(other, title="By Other", slug="by-other")

        response = self.client.get(reverse("public:author-detail", args=["author"]))

        self.assertContains(response, "By Author")
        self.assertNotContains(response, "By Other")

    def test_author_with_no_published_posts_404s(self):
        make_user("ghost@example.com", "ghost")
        response = self.client.get(reverse("public:author-detail", args=["ghost"]))
        self.assertEqual(response.status_code, 404)

    def test_author_with_only_draft_posts_404s(self):
        make_user("drafter@example.com", "drafter")
        drafter = make_user("drafter2@example.com", "drafter2")
        make_post(drafter, title="Never Published", slug="never-published", status=PostStatus.DRAFT)

        response = self.client.get(reverse("public:author-detail", args=["drafter2"]))
        self.assertEqual(response.status_code, 404)

    def test_unknown_author_username_404s(self):
        response = self.client.get(reverse("public:author-detail", args=["totally-made-up-username"]))
        self.assertEqual(response.status_code, 404)


class StaticPagesTests(TestCase):
    def test_about_page(self):
        self.assertEqual(self.client.get(reverse("public:about")).status_code, 200)

    def test_privacy_page(self):
        self.assertEqual(self.client.get(reverse("public:privacy")).status_code, 200)

    def test_terms_page(self):
        self.assertEqual(self.client.get(reverse("public:terms")).status_code, 200)

    def test_feed_returns_rss_xml(self):
        response = self.client.get(reverse("public:feed"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("xml", response["Content-Type"])

    def test_feed_only_includes_published_posts(self):
        author = make_user("author@example.com", "author")
        published_post(author, title="Feed Me", slug="feed-me")
        make_post(author, title="Not In Feed", slug="not-in-feed", status=PostStatus.DRAFT)

        response = self.client.get(reverse("public:feed"))

        self.assertContains(response, "Feed Me")
        self.assertNotContains(response, "Not In Feed")

    def test_custom_404_page(self):
        response = self.client.get("/this-url-does-not-exist/")
        self.assertEqual(response.status_code, 404)
