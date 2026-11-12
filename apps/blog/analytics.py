"""Aggregated content analytics — one row per (post, day), never one row
per page view. Backs the dashboard's Top Posts widget and each post's
"Views: all-time / 7 days / 30 days" breakdown (see the Step 7 spec's
explicit "do not create one database row for every page view" guidance).

Recording is gated behind `SiteSetting.analytics_enabled` — turning
analytics off in Settings stops new rows from being written at all, not
just from being displayed.
"""
from django.db.models import F, Sum
from django.utils import timezone


def analytics_enabled():
    from apps.core.models import SiteSetting

    return SiteSetting.load().analytics_enabled


def record_post_view(post):
    if not analytics_enabled():
        return

    from .models import PostViewDaily

    today = timezone.localdate()
    obj, created = PostViewDaily.objects.get_or_create(post=post, date=today, defaults={"views": 1})
    if not created:
        PostViewDaily.objects.filter(pk=obj.pk).update(views=F("views") + 1)


def post_view_stats(post):
    """All-time comes straight from `Post.views_count` (an exact running
    total, unaffected by whether the daily table has been pruned yet);
    the 7/30-day windows sum the daily aggregate.
    """
    from .models import PostViewDaily

    today = timezone.localdate()

    def _sum_since(days):
        since = today - timezone.timedelta(days=days - 1)
        result = PostViewDaily.objects.filter(post=post, date__gte=since).aggregate(total=Sum("views"))
        return result["total"] or 0

    return {
        "all_time": post.views_count,
        "last_7_days": _sum_since(7),
        "last_30_days": _sum_since(30),
    }


def top_posts(limit=5, days=None):
    """Real posts ranked by real view counts — all-time uses
    `Post.views_count` directly (cheap, already indexed via ordering);
    a `days` window sums the daily aggregate instead, since a windowed
    ranking can't be answered from the all-time counter alone.
    """
    from .models import Post

    if days is None:
        return list(
            Post.objects.filter(deleted_at__isnull=True, views_count__gt=0)
            .select_related("author").order_by("-views_count")[:limit]
        )

    from .models import PostViewDaily

    since = timezone.localdate() - timezone.timedelta(days=days - 1)
    ranked_ids = list(
        PostViewDaily.objects.filter(date__gte=since)
        .values("post_id").annotate(total=Sum("views"))
        .order_by("-total")[:limit]
        .values_list("post_id", flat=True)
    )
    posts_by_id = Post.objects.filter(pk__in=ranked_ids).select_related("author").in_bulk()
    return [posts_by_id[pk] for pk in ranked_ids if pk in posts_by_id]


def prune_post_view_daily(older_than_days):
    from .models import PostViewDaily

    cutoff = timezone.localdate() - timezone.timedelta(days=older_than_days)
    deleted_count, _ = PostViewDaily.objects.filter(date__lt=cutoff).delete()
    return deleted_count
