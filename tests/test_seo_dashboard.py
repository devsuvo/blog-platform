import datetime

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import ADMIN, SUPER_ADMIN
from apps.blog.models import Category, PostStatus
from apps.core.models import NotFoundLog, SiteSetting
from apps.public.models import Redirect

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class SEOHealthDashboardAccessTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dashboard:seo-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_non_staff_user_redirected(self):
        make_user("regular@example.com", "regular")
        self.client.login(username="regular@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:seo-dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_staff_user_can_view(self):
        make_user("admin@example.com", "admin", role=ADMIN)
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:seo-dashboard"))
        self.assertEqual(response.status_code, 200)


class SEOHealthComputationTests(TestCase):
    """`compute_seo_health` backs both the dashboard and the management
    commands — verify its numbers are real, not placeholders.
    """

    def setUp(self):
        super().setUp()
        self.author = make_user("author@example.com", "author")

    def test_missing_meta_description_counts_posts_with_no_description_and_no_excerpt(self):
        from apps.public.seo_health import compute_seo_health

        published_post(self.author, title="No Description", slug="no-description", excerpt="", meta_description="")
        published_post(self.author, title="Has Excerpt", slug="has-excerpt", excerpt="Something.", meta_description="")

        health = compute_seo_health()

        self.assertEqual(health["missing_meta_description"], 1)

    def test_indexed_posts_excludes_noindex_flagged_posts(self):
        from apps.public.seo_health import compute_seo_health

        published_post(self.author, title="Indexed", slug="indexed-post")
        published_post(self.author, title="Not Indexed", slug="not-indexed-post", robots_index=False)

        health = compute_seo_health()

        self.assertEqual(health["indexed_posts"], 1)

    def test_empty_categories_are_counted(self):
        from apps.public.seo_health import compute_seo_health

        Category.objects.create(name="Empty", slug="empty-cat")
        category = Category.objects.create(name="Full", slug="full-cat")
        published_post(self.author, title="In Category", slug="in-full-cat", category=category)

        health = compute_seo_health()

        self.assertEqual(health["empty_categories"], 1)

    def test_broken_redirect_is_detected(self):
        from apps.public.seo_health import compute_seo_health

        Redirect.objects.create(old_path="/broken/", new_path="/this-path-does-not-resolve/")

        health = compute_seo_health()

        self.assertEqual(health["redirects_broken"], 1)

    def test_working_redirect_is_not_flagged_broken(self):
        from apps.public.seo_health import compute_seo_health

        Redirect.objects.create(old_path="/working/", new_path="/blog/")

        health = compute_seo_health()

        self.assertEqual(health["redirects_broken"], 0)

    def test_duplicate_slug_group_detected(self):
        from apps.public.seo_health import compute_seo_health

        published_post(self.author, title="Post", slug="my-post")
        published_post(self.author, title="Post 2", slug="my-post-2")

        health = compute_seo_health()

        self.assertIn("my-post", health["duplicate_slug_groups"])

    def test_dashboard_shows_real_computed_numbers(self):
        make_user("admin@example.com", "admin", role=ADMIN)
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)
        published_post(self.author, title="Visible In Health", slug="visible-in-health")

        response = self.client.get(reverse("dashboard:seo-dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["health"]["published_posts"], 1)


class PerPostSEOCheckerTests(TestCase):
    def setUp(self):
        super().setUp()
        from apps.accounts.roles import AUTHOR

        self.author = make_user("author@example.com", "author", role=AUTHOR)
        grant_perms(self.author, "add_post", "change_post", "view_post")
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

    def test_short_content_flagged_as_under_minimum(self):
        from apps.blog.services import analyze_post_seo

        post = make_post(self.author, title="Short", slug="short-seo-check", content="<p>Too short.</p>")

        checks = analyze_post_seo(post)

        content_check = next(c for c in checks if c["label"] == "Content Length")
        self.assertFalse(content_check["ok"])

    def test_long_content_passes_length_check(self):
        from apps.blog.services import analyze_post_seo

        content = "<h2>Section</h2><p>" + ("word " * 350) + "</p>"
        post = make_post(self.author, title="Long", slug="long-seo-check", content=content)

        checks = analyze_post_seo(post)

        content_check = next(c for c in checks if c["label"] == "Content Length")
        self.assertTrue(content_check["ok"])

    def test_post_edit_page_shows_seo_checklist(self):
        post = make_post(self.author, title="Checklist Post", slug="checklist-post", content="<p>Body</p>")

        response = self.client.get(reverse("dashboard:post-edit", args=[post.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertIn("seo_checks", response.context)


class SEOSettingsFormTests(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_non_staff_user_is_redirected(self):
        make_user("regular@example.com", "regular")
        self.client.login(username="regular@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:settings-section", args=["seo"]))

        self.assertEqual(response.status_code, 302)

    def test_staff_user_without_permission_gets_403(self):
        # Staff (so it clears the is_staff gate) but no core.change_sitesetting
        # permission granted — this is what actually exercises permission_required.
        make_user("staffer@example.com", "staffer", role=ADMIN)
        self.client.login(username="staffer@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:settings-section", args=["seo"]))

        self.assertEqual(response.status_code, 403)

    def test_authorized_user_can_update_seo_settings(self):
        user = make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:settings-section", args=["seo"]), {
            "site_title": "New Title", "site_name": "New Site Name", "site_description": "New description.",
            "default_meta_description": "Fallback description.", "default_robots": "index, follow",
            "default_og_title": "", "default_og_description": "",
            "twitter_username": "@myhandle", "canonical_domain": "https://example.com",
        })

        self.assertEqual(response.status_code, 302)
        settings_obj = SiteSetting.load()
        self.assertEqual(settings_obj.site_name, "New Site Name")
        self.assertEqual(settings_obj.twitter_username, "myhandle")

    def test_updating_settings_invalidates_settings_cache(self):
        user = make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)
        SiteSetting.load()  # warm the cache
        from apps.core.services import site_settings_cache_key
        self.assertIsNotNone(cache.get(site_settings_cache_key()))

        self.client.post(reverse("dashboard:settings-section", args=["seo"]), {
            "site_title": "", "site_name": "Changed Name", "site_description": "",
            "default_meta_description": "", "default_robots": "index, follow",
            "default_og_title": "", "default_og_description": "",
            "twitter_username": "", "canonical_domain": "",
        })

        self.assertEqual(SiteSetting.load().site_name, "Changed Name")

    def test_updated_site_name_reflected_on_public_pages(self):
        user = make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)
        self.client.post(reverse("dashboard:settings-section", args=["seo"]), {
            "site_title": "", "site_name": "Rebranded Blog", "site_description": "",
            "default_meta_description": "", "default_robots": "index, follow",
            "default_og_title": "", "default_og_description": "",
            "twitter_username": "", "canonical_domain": "",
        })

        response = self.client.get("/")
        self.assertContains(response, "Rebranded Blog")

    def test_canonical_domain_without_scheme_is_rejected(self):
        make_user("owner@example.com", "owner", role=SUPER_ADMIN)
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:settings-section", args=["seo"]), {
            "site_title": "", "site_name": "X", "site_description": "",
            "default_meta_description": "", "default_robots": "index, follow",
            "default_og_title": "", "default_og_description": "",
            "twitter_username": "", "canonical_domain": "example.com",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(SiteSetting.load().canonical_domain, "")


class NotFoundLogDashboardTests(TestCase):
    def setUp(self):
        super().setUp()
        NotFoundLog.objects.create(path="/some-missing-page/", hit_count=4)

    def test_unauthorized_user_gets_403(self):
        make_user("regular@example.com", "regular")
        self.client.login(username="regular@example.com", password=DEFAULT_PASSWORD)
        response = self.client.get(reverse("dashboard:not-found-log-list"))
        self.assertEqual(response.status_code, 403)

    def test_authorized_user_sees_logged_paths(self):
        user = make_user("owner@example.com", "owner")
        grant_perms(user, "view_notfoundlog", app_label="core")
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:not-found-log-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/some-missing-page/")

    def test_dismiss_deletes_entry(self):
        entry = NotFoundLog.objects.get(path="/some-missing-page/")
        user = make_user("owner@example.com", "owner")
        grant_perms(user, "delete_notfoundlog", app_label="core")
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:not-found-log-dismiss", args=[entry.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(NotFoundLog.objects.filter(pk=entry.pk).exists())
