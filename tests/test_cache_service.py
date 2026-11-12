from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.core.cache import get_or_set_with_lock, make_key


class MakeKeyTests(TestCase):
    def test_key_includes_version_prefix(self):
        with override_settings(CACHE_VERSION="v1"):
            self.assertEqual(make_key("post", 42), "blog:v1:post:42")

    def test_bumping_version_changes_the_key(self):
        with override_settings(CACHE_VERSION="v2"):
            self.assertEqual(make_key("post", 42), "blog:v2:post:42")

    def test_multiple_parts_are_joined(self):
        self.assertIn(":category:python:posts", make_key("category", "python", "posts"))


class GetOrSetWithLockTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_cache_hit_never_calls_compute(self):
        cache.set("stampede:hit", "cached-value", 60)
        compute = lambda: (_ for _ in ()).throw(AssertionError("should not be called on a cache hit"))

        result = get_or_set_with_lock("stampede:hit", compute, 60)

        self.assertEqual(result, "cached-value")

    def test_cache_miss_computes_and_caches(self):
        calls = []

        def compute():
            calls.append(1)
            return "fresh-value"

        result = get_or_set_with_lock("stampede:miss", compute, 60)

        self.assertEqual(result, "fresh-value")
        self.assertEqual(len(calls), 1)
        self.assertEqual(cache.get("stampede:miss"), "fresh-value")

    def test_second_caller_reuses_first_callers_result_instead_of_recomputing(self):
        """Simulates the stampede scenario: the lock is already held (another
        request is computing), and the real value shows up mid-wait — the
        second caller must pick that up rather than recomputing.
        """
        cache.set("stampede:concurrent:lock", "someone-elses-token", 10)

        def compute():
            raise AssertionError("second caller should not recompute — the lock is held by someone else")

        with patch("apps.core.cache.time.sleep", side_effect=lambda _: cache.set("stampede:concurrent", "value-from-first-caller", 60)):
            result = get_or_set_with_lock("stampede:concurrent", compute, 60)

        self.assertEqual(result, "value-from-first-caller")

    def test_falls_back_to_computing_if_lock_holder_never_finishes(self):
        cache.set("stampede:stuck:lock", "stuck-token", 10)

        def compute():
            return "computed-as-fallback"

        with patch("apps.core.cache.time.sleep"), patch("apps.core.cache._LOCK_MAX_WAIT", 0.1):
            result = get_or_set_with_lock("stampede:stuck", compute, 60)

        self.assertEqual(result, "computed-as-fallback")

    def test_lock_is_released_after_successful_compute(self):
        get_or_set_with_lock("stampede:lock-release", lambda: "value", 60)
        self.assertIsNone(cache.get("stampede:lock-release:lock"))
