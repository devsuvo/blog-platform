from django.conf import settings
from django.db.models import F

from .cache import make_key
from .models import ActivityLog

# Paths that generate 404 noise with no SEO value (bot scans, asset probes) —
# never worth a database write. Keeps NotFoundLog signal, not noise.
_NOT_FOUND_IGNORE_PREFIXES = ("/static/", "/media/", "/django-admin/", "/.well-known/")
_NOT_FOUND_IGNORE_SUFFIXES = (".php", ".env", ".git", ".xml.gz", "favicon.ico")


def site_settings_cache_ttl():
    return getattr(settings, "CACHE_TTL_SITE_SETTINGS", 3600)


def site_settings_cache_key():
    return make_key("site-settings")


def get_client_ip(request):
    if request is None:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_activity(action, actor=None, target=None, description="", metadata=None, request=None):
    """Write one immutable audit trail entry.

    Never pass passwords, hashes, tokens, or session keys in `metadata` —
    this table is readable through the admin panel's Activity Logs screen.
    """
    ActivityLog.objects.create(
        actor=actor if (actor is not None and getattr(actor, "is_authenticated", True)) else None,
        action=action,
        description=description,
        target=target,
        metadata=metadata or {},
        ip_address=get_client_ip(request),
    )


def record_not_found(request):
    """Sample a 404 into NotFoundLog — skipped for static/media/admin/bot-scan
    noise so the table stays a useful signal of real broken links, not a
    firehose of every scanner request the site receives.
    """
    from .models import NotFoundLog

    path = request.path[:500]
    if path.startswith(_NOT_FOUND_IGNORE_PREFIXES) or path.lower().endswith(_NOT_FOUND_IGNORE_SUFFIXES):
        return

    referrer = request.META.get("HTTP_REFERER", "")[:500]
    obj, created = NotFoundLog.objects.get_or_create(path=path, defaults={"referrer": referrer})
    if not created:
        NotFoundLog.objects.filter(pk=obj.pk).update(hit_count=F("hit_count") + 1)
        if referrer:
            obj.referrer = referrer
            obj.save(update_fields=["referrer"])


def prune_not_found_logs(older_than_days=90):
    """Delete 404 log entries not seen recently — the table exists to
    surface *current* broken links, not to be a permanent record (that's
    what ActivityLog is for). Age-only cutoff, not hit_count: a path
    that's still getting hit updates `last_seen` and survives regardless
    of how old the row originally was.
    """
    from django.utils import timezone

    from .models import NotFoundLog

    cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
    deleted_count, _ = NotFoundLog.objects.filter(last_seen__lt=cutoff).delete()
    return deleted_count


def prune_activity_logs(older_than_days):
    """Delete ActivityLog rows older than the given cutoff. Deliberately
    requires an explicit argument (no default) and is never called from
    a scheduled task — this is an audit trail, and silently pruning it on
    a timer is exactly the kind of "too aggressive" cleanup the retention
    policy should be a conscious operator decision, not an app default.
    Run via `manage.py prune_activity_logs --older-than-days N`.
    """
    from django.utils import timezone

    cutoff = timezone.now() - timezone.timedelta(days=older_than_days)
    deleted_count, _ = ActivityLog.objects.filter(created_at__lt=cutoff).delete()
    return deleted_count
