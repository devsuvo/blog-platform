"""
Base settings shared by every environment.

Environment-specific files (development.py, production.py, testing.py)
import * from here and override only what needs to differ.
"""
from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="", cast=Csv())

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
]

THIRD_PARTY_APPS = [
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.core",
    "apps.blog",
    "apps.dashboard",
    "apps.public",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.AccountStatusMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.public.middleware.RedirectMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.dashboard.context_processors.admin_panel",
                "apps.public.context_processors.site",
                "apps.public.context_processors.seo_defaults",
                "apps.public.context_processors.nav_categories",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
#
# DATABASE_URL drives everything so the same code path works for SQLite in
# local development and PostgreSQL in staging/production. See .env.example.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": dj_database_url.parse(
        config("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ---------------------------------------------------------------------------
# Authentication & passwords
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:index"
LOGOUT_REDIRECT_URL = "public:home"

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
#
# Static files (CSS/JS shipped with the codebase) and media files
# (user-uploaded content) are kept strictly separate.
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="webmaster@localhost")

# ---------------------------------------------------------------------------
# Public site identity — used in <title> suffixes, footer, Open Graph,
# JSON-LD, and where the contact form's notification email is sent.
# ---------------------------------------------------------------------------
SITE_NAME = config("SITE_NAME", default="The Blog Platform")
SITE_DESCRIPTION = config(
    "SITE_DESCRIPTION",
    default="Ideas, tutorials, and insights for modern developers.",
)
CONTACT_EMAIL = config("CONTACT_EMAIL", default=DEFAULT_FROM_EMAIL)

# The one place the site's canonical domain is configured. When set
# (production should always set it), every canonical/OG/JSON-LD URL is
# built from this instead of the current request — so a proxy header
# mixup, or someone hitting the site by IP/a staging alias, can never
# leak an inconsistent http/https or www/non-www URL into indexed pages.
# Empty in local dev: SEO helpers fall back to request.build_absolute_uri.
SITE_URL = config("SITE_URL", default="").rstrip("/")

# ---------------------------------------------------------------------------
# Cache
#
# Overridden per-environment: LocMemCache in development/testing,
# Redis (django-redis) in production. See development.py / production.py.
#
# CACHE_VERSION is prepended to every key built through
# apps.core.cache.make_key() (see that module) — bumping it on deploy is a
# cheap way to invalidate everything at once after a change to what a key's
# *shape* means, without touching TTLs or individual invalidation call sites.
# ---------------------------------------------------------------------------
REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379/1")
CACHE_VERSION = config("CACHE_VERSION", default="v1")

# Per-resource TTLs (seconds) — deliberately different per resource rather
# than one blanket value: settings barely change (long TTL is safe), a
# listing page changes more often (short TTL bounds staleness), and every
# one of these is still backed by explicit invalidation on the actual
# write path (see apps.blog.services.invalidate_*) — the TTL is a safety
# net for anything that invalidation misses, not the primary mechanism.
CACHE_TTL_SITE_SETTINGS = config("CACHE_TTL_SITE_SETTINGS", default=3600, cast=int)
CACHE_TTL_HOMEPAGE = config("CACHE_TTL_HOMEPAGE", default=120, cast=int)
CACHE_TTL_LISTING = config("CACHE_TTL_LISTING", default=300, cast=int)
CACHE_TTL_POST_CONTENT = config("CACHE_TTL_POST_CONTENT", default=3600, cast=int)
CACHE_TTL_SITEMAP = config("CACHE_TTL_SITEMAP", default=1800, cast=int)
CACHE_TTL_RSS = config("CACHE_TTL_RSS", default=600, cast=int)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ---------------------------------------------------------------------------
# Celery / Celery Beat
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Default retry policy for tasks that opt into it via
# `autoretry_for=(...)`. Individual tasks still choose *which* exceptions
# count as transient (see apps/blog/tasks.py, apps/core/tasks.py) — this
# just keeps the backoff/ceiling consistent across all of them.
CELERY_TASK_DEFAULT_RETRY_DELAY = 30  # seconds, doubled by retry_backoff
CELERY_TASK_MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Security (baseline; environment files tighten this further)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # front-end JS needs to read this for AJAX requests carrying the token
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Required when the site is served over HTTPS behind a reverse proxy and
# accepts POSTs from a browser: Django's CSRF check compares the request's
# Origin/Referer against this list because SECURE_PROXY_SSL_HEADER makes
# Django *think* the request arrived over HTTPS, which changes what counts
# as "same origin". Empty by default (fine for plain HTTP local dev);
# production.py's own settings validate this is actually set.
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Every handler gets the request_id filter, and every formatter includes
# {request_id} — Python's logging raises if a format field is missing
# from a record, so this can't be applied selectively per-handler.
# production.py switches every handler's formatter to "json"; local dev
# keeps "verbose" because it's easier to read in a terminal.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.logging_utils.RequestIDLogFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} [{request_id}] {message}",
            "style": "{",
        },
        "json": {
            "()": "apps.core.logging_utils.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "verbose",
        },
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "application.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "filters": ["request_id"],
            "formatter": "verbose",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "filters": ["request_id"],
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "app_file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "app_file"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "security_file"],
            "level": "WARNING",
            "propagate": False,
        },
        # django-redis logs a warning here when IGNORE_EXCEPTIONS swallows a
        # connection error (production.py) — without an explicit logger
        # entry it would still reach the console via the root logger, but
        # not the rotating file handlers the rest of the app relies on.
        "django_redis": {
            "handlers": ["console", "app_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "app_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
