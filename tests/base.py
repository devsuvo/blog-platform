from django.core.cache import cache
from django.test import TestCase


class CacheClearingTestCase(TestCase):
    """Base for tests touching public views: LocMemCache is a process-wide
    singleton that Django's per-test transaction rollback does NOT reset,
    so a cached `latest_posts`/`nav_categories`/etc. list from an earlier
    test's database state can otherwise leak into this one.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
