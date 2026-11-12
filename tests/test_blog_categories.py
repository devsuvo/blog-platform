from django.test import TestCase
from django.urls import reverse

from apps.blog.models import Category, Post

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class CategoryCreationTests(TestCase):
    def setUp(self):
        self.user = make_user("admin@example.com", "admin1")
        grant_perms(self.user, "add_category", "view_category", "change_category", "delete_category")
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)

    def test_category_creation_auto_slugs(self):
        response = self.client.post(reverse("dashboard:category-create"), {
            "name": "Web Development", "slug": "", "description": "", "parent": "",
            "meta_title": "", "meta_description": "",
        })
        self.assertEqual(response.status_code, 302)
        category = Category.objects.get()
        self.assertEqual(category.slug, "web-development")

    def test_unique_slug_enforced(self):
        Category.objects.create(name="Existing", slug="existing")
        response = self.client.post(reverse("dashboard:category-create"), {
            "name": "Another", "slug": "existing", "description": "", "parent": "",
            "meta_title": "", "meta_description": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Category.objects.count(), 1)

    def test_post_category_relationship(self):
        category = Category.objects.create(name="Tech", slug="tech")
        post = make_post(self.user, title="A post", slug="a-post", category=category)

        self.assertEqual(post.category, category)
        self.assertIn(post, category.posts.all())

    def test_deleting_category_uncategorizes_posts_instead_of_deleting_them(self):
        category = Category.objects.create(name="Tech", slug="tech")
        post = make_post(self.user, title="A post", slug="a-post", category=category)

        self.client.post(reverse("dashboard:category-delete", args=[category.pk]))

        post.refresh_from_db()
        self.assertIsNone(post.category)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())
