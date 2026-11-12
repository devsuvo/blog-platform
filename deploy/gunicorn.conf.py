"""Gunicorn configuration for production. Run with:

    gunicorn config.wsgi:application -c deploy/gunicorn.conf.py

Every value below is overridable via environment variable so the same
config file works across environments without editing code — see the
`config(...)` calls. Defaults are reasonable starting points, not
guarantees; watch actual CPU/memory/latency under real traffic and adjust.
"""
import multiprocessing

from decouple import config

bind = config("GUNICORN_BIND", default="0.0.0.0:8000")

# Rule of thumb for a CPU-bound-ish Django app: (2 x CPU cores) + 1. This
# is a *starting point* — I/O-heavy workloads (mostly waiting on the DB)
# can often go higher; memory-constrained hosts may need to go lower.
# Measure before changing this in either direction.
workers = config("GUNICORN_WORKERS", default=multiprocessing.cpu_count() * 2 + 1, cast=int)
worker_class = config("GUNICORN_WORKER_CLASS", default="sync")

# A request stuck longer than this is killed and the worker restarted —
# protects against one hung request (e.g. a stalled upstream call)
# starving the whole worker. Raise it only for routes that are legitimately
# slow (e.g. a large report), never as a blanket fix for a slow query.
timeout = config("GUNICORN_TIMEOUT", default=30, cast=int)
graceful_timeout = config("GUNICORN_GRACEFUL_TIMEOUT", default=30, cast=int)
keepalive = config("GUNICORN_KEEPALIVE", default=5, cast=int)

# Recycle workers periodically — bounds the damage of a slow memory leak
# without needing to find and fix it before the next deploy. The jitter
# spreads the restarts so they don't all happen at once under load.
max_requests = config("GUNICORN_MAX_REQUESTS", default=1000, cast=int)
max_requests_jitter = config("GUNICORN_MAX_REQUESTS_JITTER", default=50, cast=int)

# Logs to stdout/stderr — the process supervisor (systemd, Docker, etc.)
# owns log capture/rotation from there. The app's own file-based logs
# (logs/application.log, logs/security.log) are the application-level
# log, not Gunicorn's access log; keep both.
accesslog = "-"
errorlog = "-"
loglevel = config("GUNICORN_LOG_LEVEL", default="info")

# Reject anything absurdly large before it reaches Django at all.
limit_request_line = 8190
limit_request_fields = 100
