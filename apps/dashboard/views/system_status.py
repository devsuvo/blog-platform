import platform
import uuid

import django
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.cache import cache
from django.db import connection
from django.shortcuts import render


def _database_status():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {"label": "Healthy", "ok": True, "detail": connection.vendor}
    except Exception as exc:  # pragma: no cover - defensive, hard to trigger in tests
        return {"label": "Unavailable", "ok": False, "detail": str(exc)[:200]}


def _cache_status():
    try:
        probe_key = f"system-status-probe:{uuid.uuid4().hex}"
        cache.set(probe_key, "1", 5)
        ok = cache.get(probe_key) == "1"
        cache.delete(probe_key)
        backend = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
        return {"label": "Healthy" if ok else "Unavailable", "ok": ok, "detail": backend}
    except Exception as exc:  # pragma: no cover - defensive
        return {"label": "Unavailable", "ok": False, "detail": str(exc)[:200]}


def _celery_status():
    """No broker ping here — that would add a network round trip (and a
    hard dependency on Celery being reachable) to a page that's meant to
    be a quick glance, not a deep probe. Eager-mode + the periodic task
    table are enough to answer "is this configured the way I expect."
    """
    eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
    return {
        "label": "Eager (synchronous, no broker)" if eager else "Configured",
        "ok": True,
        "detail": "Tasks run inline — fine for dev, never production." if eager else "Broker-backed",
    }


@login_required
@user_passes_test(lambda u: u.is_superuser, login_url="dashboard:index")
def system_status(request):
    from django_celery_beat.models import PeriodicTask

    periodic_tasks = PeriodicTask.objects.exclude(name="celery.backend_cleanup").order_by("name")

    context = {
        "page_title": "System Status",
        "django_version": django.get_version(),
        "python_version": platform.python_version(),
        "debug": settings.DEBUG,
        "database": _database_status(),
        "cache": _cache_status(),
        "celery": _celery_status(),
        "periodic_tasks": periodic_tasks,
    }
    return render(request, "admin_panel/system/status.html", context)
