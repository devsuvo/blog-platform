from django.http import JsonResponse
from django.shortcuts import render

_ERROR_CONTEXT = {"robots": "noindex, nofollow", "canonical_path": None}


def health_check(request):
    """Lightweight liveness endpoint for load balancers / uptime monitors.

    Deliberately reports no database/cache/queue state so it never leaks
    internal infrastructure details to an unauthenticated caller. "Is the
    process up and serving requests" — nothing more. See `readiness_check`
    for "can it actually do its job."
    """
    return JsonResponse({"status": "ok"})


def readiness_check(request):
    """Can this instance actually serve traffic — DB and cache both
    reachable? Used by an orchestrator (e.g. Kubernetes readinessProbe) to
    decide whether to route traffic here, distinct from liveness (whether
    to restart the process at all).

    Still minimal on purpose: booleans only, never a hostname, port,
    credential, or the underlying exception's text — an unauthenticated
    caller learns "up" or "down", nothing about *why*, which is what the
    application logs (with the request's ID) are for.
    """
    import uuid

    from django.core.cache import cache
    from django.db import connection

    database_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database_ok = True
    except Exception:
        pass

    cache_ok = False
    try:
        probe_key = f"readiness-probe:{uuid.uuid4().hex}"
        cache.set(probe_key, "1", 5)
        cache_ok = cache.get(probe_key) == "1"
        cache.delete(probe_key)
    except Exception:
        pass

    ready = database_ok and cache_ok
    body = {"status": "ready" if ready else "unavailable", "database": database_ok, "cache": cache_ok}
    return JsonResponse(body, status=200 if ready else 503)


def error_400(request, exception=None):
    return render(request, "errors/400.html", _ERROR_CONTEXT, status=400)


def error_403(request, exception=None):
    return render(request, "errors/403.html", _ERROR_CONTEXT, status=403)


def error_404(request, exception=None):
    # 404 sampling into NotFoundLog happens in RedirectMiddleware, which
    # already has to inspect every 404 to check for a matching redirect —
    # doing it there avoids recording a path that's about to be redirected.
    return render(request, "errors/404.html", _ERROR_CONTEXT, status=404)


def error_429(request, exception=None):
    return render(request, "errors/429.html", _ERROR_CONTEXT, status=429)


def error_500(request):
    # Built fresh per call, never mutating the shared _ERROR_CONTEXT dict —
    # request_id is per-request and must not leak between requests.
    context = {**_ERROR_CONTEXT, "request_id": getattr(request, "request_id", None)}
    return render(request, "errors/500.html", context, status=500)
