from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

if not ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set via environment in production.")

if not CSRF_TRUSTED_ORIGINS:  # noqa: F405
    raise ImproperlyConfigured(
        "CSRF_TRUSTED_ORIGINS must be set via environment in production, "
        "e.g. https://example.com,https://www.example.com"
    )

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---------------------------------------------------------------------------
# Transport security
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)  # noqa: F405
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)  # noqa: F405
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = config("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool)  # noqa: F405
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)  # noqa: F405
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Cache — Redis-backed in production.
#
# IGNORE_EXCEPTIONS implements graceful Redis failure: if Redis is
# unreachable, django-redis swallows the connection error and
# cache.get() returns None (a miss) / cache.set() silently no-ops,
# instead of turning a cache blip into a 500 on every page. Every cache
# read in this codebase already treats None as "go to the database" —
# that fallback is what makes this safe, not a special case here.
# LOG_IGNORED_EXCEPTIONS sends the swallowed error to the "django_redis"
# logger (see LOGGING in base.py) so an outage is still visible in logs,
# just not in a user-facing 500.
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,  # noqa: F405
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
        },
    }
}
DJANGO_REDIS_IGNORE_EXCEPTIONS = True
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

# ---------------------------------------------------------------------------
# Logging — same handlers/loggers as base.py, switched to one-JSON-object-
# per-line so a log aggregator can parse them without a vendor-specific
# shipper config. Levels are unchanged: still INFO/WARNING, never DEBUG —
# a busy production site would otherwise drown its own disk in noise.
# ---------------------------------------------------------------------------
for _handler in LOGGING["handlers"].values():  # noqa: F405
    _handler["formatter"] = "json"
del _handler
