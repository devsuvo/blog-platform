import logging

from celery import shared_task
from django.db import DatabaseError, transaction
from django.utils import timezone

logger = logging.getLogger("apps.blog")


@shared_task(
    autoretry_for=(DatabaseError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def publish_scheduled_posts():
    """Publish every SCHEDULED post whose time has arrived.

    Idempotent by construction: the UPDATE's WHERE clause re-checks
    status=SCHEDULED, so if this task somehow runs twice concurrently (or
    Celery redelivers it) the second run's update matches zero rows for
    posts the first run already flipped to PUBLISHED — no duplicate
    publish events, no double cache invalidation race.

    Retries only on `DatabaseError` (a dropped connection, a deadlock —
    transient) with exponential backoff; anything else (a bug, bad data)
    fails once rather than retrying forever. Cache invalidation happens
    after the `atomic()` block above has already committed, never before —
    a crash mid-task can leave a post published with a stale cache for one
    more request, never the reverse (cache cleared for a publish that
    then rolled back).
    """
    from apps.core.models import ActivityAction
    from apps.core.services import log_activity

    from .models import Post, PostStatus
    from .services import invalidate_post_caches

    now = timezone.now()
    published_count = 0

    with transaction.atomic():
        due_ids = list(
            Post.objects.select_for_update(skip_locked=True)
            .filter(status=PostStatus.SCHEDULED, scheduled_at__lte=now)
            .values_list("pk", flat=True)
        )
        if due_ids:
            published_count = Post.objects.filter(
                pk__in=due_ids, status=PostStatus.SCHEDULED
            ).update(status=PostStatus.PUBLISHED, published_at=now)

    for post in Post.objects.filter(pk__in=due_ids).select_related("author", "category"):
        invalidate_post_caches(post)
        log_activity(
            ActivityAction.POST_PUBLISHED,
            actor=None,
            target=post,
            description=f"Auto-published scheduled post '{post.title}'",
            metadata={"trigger": "celery_beat"},
        )

    if published_count:
        logger.info("publish_scheduled_posts: published %s post(s)", published_count)

    return published_count
