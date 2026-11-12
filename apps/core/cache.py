"""Centralized cache key building and stampede protection.

Every cache key in the project should be built through `make_key()` — it
prepends the app-wide `CACHE_VERSION`, so bumping that one setting on
deploy invalidates every key at once after a change to what a key's shape
or contents mean, without having to touch each call site or flush Redis
wholesale (see item 13/15: never clear the entire cache).

This module intentionally has no dependency on `apps.blog` or
`apps.core.models` — it's imported by both, so it has to stay at the
bottom of the dependency graph to avoid circular imports.
"""
import logging
import time
import uuid

from django.core.cache import cache

logger = logging.getLogger("apps.core.cache")

_LOCK_TTL = 10  # seconds — long enough to cover a real recompute, short enough that a crashed holder self-heals fast
_LOCK_POLL_INTERVAL = 0.05
_LOCK_MAX_WAIT = 2.0  # seconds


def make_key(*parts):
    """Build a versioned, namespaced cache key, e.g. make_key("post", 42)
    -> "blog:v1:post:42". Bump settings.CACHE_VERSION to invalidate
    everything built through this function at once.
    """
    from django.conf import settings

    version = getattr(settings, "CACHE_VERSION", "v1")
    return "blog:" + version + ":" + ":".join(str(part) for part in parts)


def get_or_set_with_lock(key, compute_fn, ttl):
    """Stampede-safe version of cache.get_or_set().

    Plain get-or-set lets every concurrent request that misses the cache
    run `compute_fn` at once — fine for cheap lookups, dangerous for a
    page like the homepage under real traffic the instant a popular key
    expires ("dogpile"/thundering-herd). Here, only the first caller to
    miss acquires a short-lived lock (via `cache.add`, which is atomic on
    Redis — that's the whole mechanism, no separate lock server needed)
    and actually recomputes; everyone else polls the real key briefly.

    If the lock holder is slow or crashes, waiters fall through to
    computing it themselves after `_LOCK_MAX_WAIT` rather than blocking
    forever or serving stale data indefinitely — better one redundant
    computation than a stuck page.
    """
    value = cache.get(key)
    if value is not None:
        return value

    lock_key = key + ":lock"
    token = uuid.uuid4().hex
    acquired = cache.add(lock_key, token, _LOCK_TTL)

    if acquired:
        try:
            value = compute_fn()
            cache.set(key, value, ttl)
            return value
        finally:
            # Only clear the lock if it's still ours — an expired-then-
            # reacquired lock belongs to someone else's compute now.
            if cache.get(lock_key) == token:
                cache.delete(lock_key)

    waited = 0.0
    while waited < _LOCK_MAX_WAIT:
        time.sleep(_LOCK_POLL_INTERVAL)
        waited += _LOCK_POLL_INTERVAL
        value = cache.get(key)
        if value is not None:
            return value

    logger.info("cache stampede fallback: computing %s without the lock after %.1fs wait", key, waited)
    return compute_fn()
