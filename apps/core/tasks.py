import logging

from celery import shared_task
from django.core.management import call_command
from django.db import DatabaseError

logger = logging.getLogger("apps.core")


@shared_task(
    autoretry_for=(DatabaseError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def cleanup_old_data():
    """Daily housekeeping: expired sessions, stale 404 log entries, and
    (per the configured retention window) old daily view-count rows and
    search-query stats.

    Idempotent — re-running it early or twice just finds fewer (or zero)
    rows to delete the second time, never a problem. Deliberately does
    NOT touch ActivityLog (see `prune_activity_logs` for why that's a
    separate, manual, explicit-cutoff operation) or media/uploaded files.
    """
    from apps.blog.analytics import prune_post_view_daily
    from apps.core.models import SiteSetting
    from apps.public.services import prune_search_query_stats

    from .services import prune_not_found_logs

    call_command("clearsessions")  # no-op when SESSION_ENGINE is cache-backed (production)

    deleted_logs = prune_not_found_logs()
    if deleted_logs:
        logger.info("cleanup_old_data: pruned %s stale 404 log entr%s", deleted_logs, "y" if deleted_logs == 1 else "ies")

    retention_days = SiteSetting.load().analytics_retention_days
    deleted_views = prune_post_view_daily(older_than_days=retention_days)
    deleted_search_stats = prune_search_query_stats(older_than_days=retention_days)
    if deleted_views:
        logger.info("cleanup_old_data: pruned %s daily view-count row(s)", deleted_views)
    if deleted_search_stats:
        logger.info("cleanup_old_data: pruned %s search query stat(s)", deleted_search_stats)

    return {
        "not_found_logs_pruned": deleted_logs,
        "post_views_pruned": deleted_views,
        "search_stats_pruned": deleted_search_stats,
    }
