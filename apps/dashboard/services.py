"""Dashboard statistics: computed for real from the database, cached as
one blob (stampede-protected — the dashboard is the page every staff
member hits first) and invalidated on the handful of events that could
actually change the numbers. Never a full cache flush; never a fake number.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Sum

from apps.accounts.models import UserStatus
from apps.blog.analytics import top_posts
from apps.blog.models import Category, Post, PostStatus, Tag
from apps.core.cache import get_or_set_with_lock, make_key

User = get_user_model()

DASHBOARD_STATS_TTL = 120  # short — this is a live-feeling page, not a report


def _can_see_all_posts(user):
    return user.is_superuser or user.has_perm("blog.change_any_post")


def dashboard_stats_cache_key(user):
    if _can_see_all_posts(user):
        return make_key("dashboard", "stats", "global")
    return make_key("dashboard", "stats", "user", user.pk)


def invalidate_dashboard_stats(author=None):
    """Called from every place a post/category/tag/user mutation could
    change a dashboard number. The global scope always changes; a
    specific author's own scope only needs clearing when it's their post.
    """
    keys = [make_key("dashboard", "stats", "global")]
    if author is not None:
        keys.append(make_key("dashboard", "stats", "user", author.pk))
    cache.delete_many(keys)


def get_dashboard_stats(user):
    return get_or_set_with_lock(
        dashboard_stats_cache_key(user), lambda: _compute_dashboard_stats(user), DASHBOARD_STATS_TTL,
    )


def _compute_dashboard_stats(user):
    posts = Post.objects.filter(deleted_at__isnull=True)
    if not _can_see_all_posts(user):
        posts = posts.filter(author=user)

    total_views = posts.aggregate(total=Sum("views_count"))["total"] or 0

    return {
        "total_posts": posts.count(),
        "published_posts": posts.filter(status=PostStatus.PUBLISHED).count(),
        "draft_posts": posts.filter(status=PostStatus.DRAFT).count(),
        "scheduled_posts": posts.filter(status=PostStatus.SCHEDULED).count(),
        "archived_posts": posts.filter(status=PostStatus.ARCHIVED).count(),
        "total_views": total_views,
        "total_categories": Category.objects.count(),
        "total_tags": Tag.objects.count(),
        "total_authors": User.objects.filter(posts__isnull=False).distinct().count(),
        "total_users": User.objects.count(),
        "active_users": User.objects.filter(status=UserStatus.ACTIVE).count(),
        "recent_posts": list(
            posts.select_related("author").order_by("-created_at")[:8]
        ),
        "top_posts": top_posts(limit=5),
    }
