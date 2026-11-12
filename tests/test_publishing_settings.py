import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import AUTHOR, SUPER_ADMIN
from apps.blog.models import PostStatus
from apps.core.models import SiteSetting

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class AllowAuthorsToPublishTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "publish_post", "view_post")
        self.post = make_post(self.author, title="My Draft", slug="my-draft")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_author_can_publish_own_post_by_default(self):
        response = self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.PUBLISHED)

    def test_disabling_the_setting_blocks_author_publishing_even_with_permission(self):
        settings_obj = SiteSetting.load()
        settings_obj.allow_authors_to_publish = False
        settings_obj.save()

        response = self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))

        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.DRAFT)

    def test_setting_does_not_affect_editors_or_admins_with_change_any_post(self):
        from apps.accounts.roles import EDITOR

        settings_obj = SiteSetting.load()
        settings_obj.allow_authors_to_publish = False
        settings_obj.save()

        editor = make_user("editor@example.com", "editor", role=EDITOR)
        grant_perms(editor, "change_post", "change_any_post", "publish_post", "view_post")
        self.client.login(username="editor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-publish", args=[self.post.pk]))

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.PUBLISHED)


class ScheduledPublishingToggleTests(TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "publish_post", "view_post")
        self.post = make_post(self.author, title="Schedulable", slug="schedulable")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_scheduling_works_by_default(self):
        future = (timezone.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("dashboard:post-schedule", args=[self.post.pk]), {
            "scheduled_at": future,
        })
        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.SCHEDULED)

    def test_disabling_scheduled_publishing_blocks_scheduling(self):
        settings_obj = SiteSetting.load()
        settings_obj.enable_scheduled_publishing = False
        settings_obj.save()

        future = (timezone.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("dashboard:post-schedule", args=[self.post.pk]), {
            "scheduled_at": future,
        })

        self.assertEqual(response.status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, PostStatus.DRAFT)


class ReadingSpeedSettingTests(TestCase):
    def test_default_reading_speed_applies(self):
        author = make_user("author@example.com", "author")
        content = "<p>" + ("word " * 450) + "</p>"
        post = make_post(author, title="Long Post", slug="long-post", content=content)
        self.assertEqual(post.reading_time, 2)  # 450 words / 225 wpm

    def test_custom_reading_speed_changes_estimate(self):
        settings_obj = SiteSetting.load()
        settings_obj.default_reading_speed_wpm = 100
        settings_obj.save()

        author = make_user("author@example.com", "author")
        content = "<p>" + ("word " * 500) + "</p>"
        post = make_post(author, title="Long Post 2", slug="long-post-2", content=content)

        self.assertEqual(post.reading_time, 5)  # 500 words / 100 wpm


class SettingsFormAccessTests(TestCase):
    def setUp(self):
        super().setUp()
        make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

    def test_general_settings_section_saves_posts_per_page(self):
        response = self.client.post(reverse("dashboard:settings-section", args=["general"]), {
            "posts_per_page": 20,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SiteSetting.load().posts_per_page, 20)

    def test_publishing_settings_section_saves(self):
        response = self.client.post(reverse("dashboard:settings-section", args=["publishing"]), {
            "enable_scheduled_publishing": "on", "default_reading_speed_wpm": 250,
        })
        self.assertEqual(response.status_code, 302)
        settings_obj = SiteSetting.load()
        self.assertFalse(settings_obj.allow_authors_to_publish)  # checkbox omitted from POST = False
        self.assertEqual(settings_obj.default_reading_speed_wpm, 250)

    def test_analytics_settings_section_saves(self):
        response = self.client.post(reverse("dashboard:settings-section", args=["analytics"]), {
            "analytics_retention_days": 60,
        })
        self.assertEqual(response.status_code, 302)
        settings_obj = SiteSetting.load()
        self.assertFalse(settings_obj.analytics_enabled)
        self.assertEqual(settings_obj.analytics_retention_days, 60)

    def test_out_of_range_posts_per_page_rejected(self):
        response = self.client.post(reverse("dashboard:settings-section", args=["general"]), {
            "posts_per_page": 500,
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(SiteSetting.load().posts_per_page, 500)
