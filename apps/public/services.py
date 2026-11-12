import logging

from django.core.exceptions import ValidationError
from django.db.models import F

from .models import Redirect, RedirectStatusCode

logger = logging.getLogger("apps.public")

_MAX_TRACKED_QUERY_LENGTH = 100


def record_slug_redirect(old_path, new_path):
    """Auto-create (or repoint) a 301 from `old_path` to `new_path` when a
    published post's slug changes — "before creating a redirect, check if
    one already exists" per spec: `update_or_create` on `old_path` handles
    that in one step instead of a separate existence check.

    Also flattens chains: any OTHER redirect that currently points at
    `old_path` gets repointed straight to `new_path`, so a post renamed
    twice (A→B, then B→C) leaves visitors of the original URL A a single
    hop to C, not a chain through the no-longer-current B.

    Validation failures (e.g. this would somehow form a loop) are logged
    and swallowed rather than raised — a redirect bookkeeping problem must
    never block the post save that triggered it.
    """
    if old_path == new_path:
        return

    try:
        # The post's new URL is a real page again now — any stale redirect
        # that used to claim "this path redirects elsewhere" would shadow it.
        Redirect.objects.filter(old_path=new_path).delete()

        entry, _created = Redirect.objects.update_or_create(
            old_path=old_path,
            defaults={"new_path": new_path, "status_code": RedirectStatusCode.PERMANENT, "is_auto": True},
        )

        chained = Redirect.objects.filter(new_path=old_path).exclude(pk=entry.pk)
        for redirect in chained:
            redirect.new_path = new_path
            try:
                redirect.save()
            except ValidationError:
                logger.warning("Could not flatten redirect chain %s -> %s", redirect.old_path, new_path)
    except ValidationError:
        logger.warning("Could not auto-create redirect %s -> %s (validation failed)", old_path, new_path)


def record_search_query(query):
    """Aggregate a search query into `SearchQueryStat` — normalized
    (lowercased/stripped) and length-capped *before* it ever becomes part
    of a cache/DB key, so a malicious or accidental flood of unique junk
    queries can't explode the table into one row per garbage string.
    Gated behind Settings > Analytics > "Track search"; a no-op when off.
    """
    from apps.core.models import SiteSetting

    from .models import SearchQueryStat

    if not SiteSetting.load().track_search:
        return

    normalized = (query or "").strip().lower()[:_MAX_TRACKED_QUERY_LENGTH]
    if not normalized:
        return

    from django.utils import timezone

    obj, created = SearchQueryStat.objects.get_or_create(query=normalized)
    if not created:
        # `last_searched_at` is `auto_now=True`, but auto_now only fires on
        # .save() — a queryset .update() has to set it explicitly, or a
        # repeatedly-searched term would look stale and get pruned anyway.
        SearchQueryStat.objects.filter(pk=obj.pk).update(hit_count=F("hit_count") + 1, last_searched_at=timezone.now())


def top_search_queries(limit=10):
    from .models import SearchQueryStat

    return list(SearchQueryStat.objects.order_by("-hit_count")[:limit])


def prune_search_query_stats(older_than_days=180):
    from django.utils import timezone

    from .models import SearchQueryStat

    cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
    deleted_count, _ = SearchQueryStat.objects.filter(last_searched_at__lt=cutoff).delete()
    return deleted_count
