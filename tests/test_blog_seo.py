from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import AUTHOR
from apps.blog.models import Post
from apps.blog.services import generate_unique_slug, unicode_slugify

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class SlugGenerationTests(TestCase):
    def test_english_title_slugifies_normally(self):
        self.assertEqual(unicode_slugify("How to Start a Blog"), "how-to-start-a-blog")

    def test_bangla_title_keeps_vowel_signs(self):
        slug = unicode_slugify("২০২৬ সালের সেরা ডিজিটাল মার্কেটিং ট্রেন্ড")
        self.assertEqual(slug, "২০২৬-সালের-সেরা-ডিজিটাল-মার্কেটিং-ট্রেন্ড")

    def test_generate_unique_slug_disambiguates_collisions(self):
        user = make_user("author@example.com", "author")
        make_post(user, title="How to Start a Blog", slug="how-to-start-a-blog")

        slug = generate_unique_slug(Post, "How to Start a Blog")

        self.assertEqual(slug, "how-to-start-a-blog-2")

    def test_bangla_post_can_be_created_end_to_end(self):
        user = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(user, "add_post", "view_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-create"), {
            "title": "২০২৬ সালের সেরা ডিজিটাল মার্কেটিং ট্রেন্ড",
            "slug": "", "excerpt": "", "content": "<p>বাংলা বিষয়বস্তু</p>",
            "category": "", "tags": [],
        })

        self.assertEqual(response.status_code, 302)
        post = Post.objects.get()
        self.assertTrue(post.slug)
        self.assertNotIn(" ", post.slug)


class SEOFieldDefaultsTests(TestCase):
    def test_new_post_defaults_are_seo_safe(self):
        user = make_user("author@example.com", "author")
        post = make_post(user, title="A post", slug="a-post")

        self.assertTrue(post.robots_index)
        self.assertTrue(post.robots_follow)
        self.assertEqual(post.canonical_url, "")
        self.assertEqual(post.meta_title, "")
        self.assertEqual(post.meta_description, "")

    def test_draft_preview_is_noindex(self):
        user = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(user, "view_post")
        post = make_post(user, title="Draft post", slug="draft-post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:post-preview", args=[post.pk]))

        self.assertContains(response, 'name="robots" content="noindex, nofollow"')
