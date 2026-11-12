from django.urls import reverse

from apps.blog.models import Tag
from apps.core.models import ActivityLog

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class TagMergeTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")
        self.python_lower = Tag.objects.create(name="python", slug="python")
        self.python3 = Tag.objects.create(name="Python3", slug="python3")
        self.python_proper = Tag.objects.create(name="Python", slug="python-tag")
        self.staff = make_user("staff@example.com", "staff")
        grant_perms(self.staff, "change_tag", "delete_tag", "view_tag")
        self.client.login(username="staff@example.com", password=DEFAULT_PASSWORD)

    def test_requires_both_change_and_delete_tag_permission(self):
        change_only = make_user("changeonly@example.com", "changeonly")
        grant_perms(change_only, "change_tag", "view_tag")
        self.client.login(username="changeonly@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:tag-merge"), {
            "source_tags": [self.python_lower.pk], "target_tag": self.python_proper.pk,
        })

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Tag.objects.filter(pk=self.python_lower.pk).exists())

    def test_merge_reassigns_posts_and_deletes_source_tags(self):
        post = make_post(self.author, title="Tagged Post", slug="tagged-post")
        post.tags.add(self.python_lower, self.python3)

        response = self.client.post(reverse("dashboard:tag-merge"), {
            "source_tags": [self.python_lower.pk, self.python3.pk], "target_tag": self.python_proper.pk,
        })

        self.assertEqual(response.status_code, 302)
        post.refresh_from_db()
        self.assertIn(self.python_proper, post.tags.all())
        self.assertFalse(Tag.objects.filter(pk=self.python_lower.pk).exists())
        self.assertFalse(Tag.objects.filter(pk=self.python3.pk).exists())

    def test_merge_does_not_create_duplicate_relationship_if_post_already_has_target(self):
        post = make_post(self.author, title="Already Tagged", slug="already-tagged")
        post.tags.add(self.python_lower, self.python_proper)  # already has both source and target

        self.client.post(reverse("dashboard:tag-merge"), {
            "source_tags": [self.python_lower.pk], "target_tag": self.python_proper.pk,
        })

        post.refresh_from_db()
        self.assertEqual(list(post.tags.filter(pk=self.python_proper.pk)), [self.python_proper])
        self.assertEqual(post.tags.count(), 1)

    def test_target_tag_cannot_be_one_of_the_source_tags(self):
        response = self.client.post(reverse("dashboard:tag-merge"), {
            "source_tags": [self.python_lower.pk, self.python_proper.pk], "target_tag": self.python_proper.pk,
        })

        self.assertEqual(response.status_code, 200)  # form re-rendered with an error, not redirected
        self.assertTrue(Tag.objects.filter(pk=self.python_lower.pk).exists())

    def test_unrelated_posts_are_not_touched(self):
        tagged_post = make_post(self.author, title="Tagged", slug="tagged-for-merge")
        tagged_post.tags.add(self.python_lower)
        untouched_post = make_post(self.author, title="Untouched", slug="untouched-post")
        untouched_post.tags.add(self.python3)  # not a source tag in this merge

        self.client.post(reverse("dashboard:tag-merge"), {
            "source_tags": [self.python_lower.pk], "target_tag": self.python_proper.pk,
        })

        untouched_post.refresh_from_db()
        self.assertIn(self.python3, untouched_post.tags.all())
        self.assertNotIn(self.python_proper, untouched_post.tags.all())

    def test_merge_is_logged(self):
        self.client.post(reverse("dashboard:tag-merge"), {
            "source_tags": [self.python_lower.pk], "target_tag": self.python_proper.pk,
        })

        self.assertTrue(ActivityLog.objects.filter(action="tag_merged").exists())
