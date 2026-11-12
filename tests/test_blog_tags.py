from django.test import TestCase
from django.urls import reverse

from apps.blog.models import Tag

from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class TagCreationTests(TestCase):
    def setUp(self):
        self.user = make_user("admin@example.com", "admin1")
        grant_perms(self.user, "add_tag", "view_tag")
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)

    def test_tag_creation_auto_slugs(self):
        response = self.client.post(reverse("dashboard:tag-create"), {"name": "Django Tips", "slug": ""})
        self.assertEqual(response.status_code, 302)
        tag = Tag.objects.get()
        self.assertEqual(tag.slug, "django-tips")

    def test_tag_name_unique(self):
        Tag.objects.create(name="Django", slug="django")
        response = self.client.post(reverse("dashboard:tag-create"), {"name": "Django", "slug": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Tag.objects.count(), 1)


class PostTagRelationshipTests(TestCase):
    def test_post_can_have_multiple_tags(self):
        user = make_user("author@example.com", "author")
        tag1 = Tag.objects.create(name="Django", slug="django")
        tag2 = Tag.objects.create(name="Python", slug="python")
        post = make_post(user, title="A post", slug="a-post")
        post.tags.set([tag1, tag2])

        self.assertEqual(post.tags.count(), 2)
        self.assertIn(post, tag1.posts.all())
        self.assertIn(post, tag2.posts.all())
