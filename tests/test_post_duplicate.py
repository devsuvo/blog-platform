import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR
from apps.blog.models import Category, Post, PostStatus, Tag

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class PostDuplicateTests(TestCase):
    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name="Python", slug="python")
        self.tag = Tag.objects.create(name="Django", slug="django")
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "view_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_duplicate_creates_a_new_draft(self):
        source = published_post(
            self.author, title="Original Post", slug="original-post", category=self.category,
            canonical_url="https://example.com/original-post/",
        )
        source.tags.add(self.tag)

        response = self.client.post(reverse("dashboard:post-duplicate", args=[source.pk]))

        self.assertEqual(response.status_code, 302)
        duplicate = Post.objects.exclude(pk=source.pk).get()
        self.assertEqual(duplicate.status, PostStatus.DRAFT)
        self.assertEqual(duplicate.title, "Original Post (copy)")
        self.assertNotEqual(duplicate.slug, source.slug)

    def test_duplicate_does_not_copy_published_at_or_canonical_url(self):
        source = published_post(
            self.author, title="Has Canonical", slug="has-canonical",
            canonical_url="https://example.com/has-canonical/",
        )

        self.client.post(reverse("dashboard:post-duplicate", args=[source.pk]))

        duplicate = Post.objects.exclude(pk=source.pk).get()
        self.assertIsNone(duplicate.published_at)
        self.assertIsNone(duplicate.scheduled_at)
        self.assertEqual(duplicate.canonical_url, "")

    def test_duplicate_copies_category_and_tags(self):
        source = make_post(self.author, title="Tagged Post", slug="tagged-post", category=self.category)
        source.tags.add(self.tag)

        self.client.post(reverse("dashboard:post-duplicate", args=[source.pk]))

        duplicate = Post.objects.exclude(pk=source.pk).get()
        self.assertEqual(duplicate.category_id, self.category.pk)
        self.assertIn(self.tag, duplicate.tags.all())

    def test_duplicate_is_owned_by_the_user_who_duplicated_it(self):
        other_author = make_user("other@example.com", "other", role=AUTHOR)
        grant_perms(other_author, "view_post")
        source = published_post(other_author, title="Someone Elses Post", slug="someone-elses-post")

        self.client.post(reverse("dashboard:post-duplicate", args=[source.pk]))

        duplicate = Post.objects.exclude(pk=source.pk).get()
        self.assertEqual(duplicate.author_id, self.author.pk)

    def test_duplicate_redirects_to_edit_page_of_the_new_post(self):
        source = make_post(self.author, title="Redirect Target", slug="redirect-target")

        response = self.client.post(reverse("dashboard:post-duplicate", args=[source.pk]))

        duplicate = Post.objects.exclude(pk=source.pk).get()
        self.assertRedirects(response, reverse("dashboard:post-edit", args=[duplicate.pk]))

    def test_cannot_duplicate_a_post_without_view_permission_or_ownership(self):
        no_perms_user = make_user("noperms@example.com", "noperms", role=AUTHOR)
        grant_perms(no_perms_user, "add_post")  # add_post only — no view_post, doesn't own the source
        other_author = make_user("other@example.com", "other", role=AUTHOR)
        source = make_post(other_author, title="Private Draft", slug="private-draft", status=PostStatus.DRAFT)

        self.client.login(username="noperms@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-duplicate", args=[source.pk]))

        self.assertEqual(response.status_code, 403)
