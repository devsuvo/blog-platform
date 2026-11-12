import datetime
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.blog.models import PostStatus
from apps.public.models import Redirect

from .helpers import make_post, make_user


def published_post(author, **extra):
    extra.setdefault("published_at", timezone.now() - datetime.timedelta(hours=1))
    extra.setdefault("status", PostStatus.PUBLISHED)
    return make_post(author, **extra)


class CheckSEOCommandTests(TestCase):
    def test_exits_zero_with_no_problems(self):
        out = StringIO()
        call_command("check_seo", stdout=out)  # should not raise
        self.assertIn("no problems found", out.getvalue())

    def test_missing_title_is_a_warning_not_a_failure(self):
        author = make_user("author@example.com", "author")
        published_post(author, title="No Meta Title", slug="no-meta-title", meta_title="")

        out = StringIO()
        call_command("check_seo", stdout=out)  # should not raise SystemExit
        self.assertIn("SEO title", out.getvalue())

    def test_broken_redirect_causes_nonzero_exit(self):
        Redirect.objects.create(old_path="/broken-cmd/", new_path="/nowhere-that-resolves/")

        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("check_seo", stdout=out)
        self.assertEqual(ctx.exception.code, 1)


class SEOReportCommandTests(TestCase):
    def test_report_runs_and_prints_sections(self):
        author = make_user("author@example.com", "author")
        published_post(author, title="Reported Post", slug="reported-post")

        out = StringIO()
        call_command("seo_report", stdout=out)

        output = out.getvalue()
        self.assertIn("SEO Report", output)
        self.assertIn("Posts:", output)
        self.assertIn("Redirects:", output)

    def test_report_never_raises_even_with_broken_redirects(self):
        Redirect.objects.create(old_path="/broken-report/", new_path="/nowhere-that-resolves/")
        out = StringIO()
        call_command("seo_report", stdout=out)  # should not raise
        self.assertIn("Broken: 1", out.getvalue())


class CheckRedirectsCommandTests(TestCase):
    def test_no_redirects_exits_clean(self):
        out = StringIO()
        call_command("check_redirects", stdout=out)  # should not raise
        self.assertIn("No problems found", out.getvalue())

    def test_broken_redirect_causes_nonzero_exit(self):
        Redirect.objects.create(old_path="/broken-check/", new_path="/nowhere-that-resolves/")
        out = StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("check_redirects", stdout=out)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("broken", out.getvalue())

    def test_working_redirect_does_not_trigger_exit(self):
        Redirect.objects.create(old_path="/working-check/", new_path="/blog/")
        out = StringIO()
        call_command("check_redirects", stdout=out)  # should not raise


class RebuildSitemapCommandTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rebuild_invalidates_and_warms_cache(self):
        from apps.blog.services import sitemap_cache_key

        cache.set(sitemap_cache_key("posts"), b"<stale/>", 300)

        out = StringIO()
        call_command("rebuild_sitemap", stdout=out)

        self.assertNotEqual(cache.get(sitemap_cache_key("posts")), b"<stale/>")
        self.assertIn("Sitemap rebuilt", out.getvalue())

    def test_no_warm_flag_only_invalidates(self):
        from apps.blog.services import sitemap_cache_key

        cache.set(sitemap_cache_key("posts"), b"<stale/>", 300)

        out = StringIO()
        call_command("rebuild_sitemap", "--no-warm", stdout=out)

        self.assertIsNone(cache.get(sitemap_cache_key("posts")))
        self.assertNotIn("Sitemap rebuilt", out.getvalue())
