# Blog Platform

A professional, SEO-first, multi-user, **content-first** blogging platform built on Django.
No featured/hero/cover image anywhere, by design — the entire public experience is
typography, content, and whitespace.

Built across eight steps, each of which layered on the last without breaking it: project
foundation and auth → a custom Admin/CMS Panel → the Blog CMS itself (posts/categories/tags,
editor, drafts/scheduling, revisions) → the public-facing site (homepage, listings, search,
RSS) → a complete SEO engine (sitemap, structured data, redirects, SEO health) → production
performance/security hardening (Redis, Celery, caching, request tracing) → an advanced CMS
layer (bulk actions, trash, preview links, tag merging, real analytics, a fifth role) → this
final production-polish pass.

## Features

- **Publishing workflow**: Draft → (optional Review) → Scheduled → Published → Archived,
  with soft-delete Trash (restore or superuser-only permanent delete), Duplicate, and
  revision history with restore-creates-a-new-revision (nothing is ever silently overwritten)
- **Five roles** (Super Admin, Admin, Editor, Author, Contributor) with **object-level**
  permissions — an Author's own drafts are theirs alone, enforced server-side, never by hiding
  a button
- **Distraction-free editor**: live word/character/reading-time counters, debounced autosave,
  browser-crash draft recovery, inline category/tag creation, a Google-style search preview,
  and a plain-language SEO Health checklist (never a fake "score")
- **Complete SEO automation**: slugs, canonical URLs, robots rules, Open Graph/Twitter Card
  (text-only — see above), JSON-LD (`BlogPosting`, `Person`, `BreadcrumbList`, `WebSite`),
  sitemap, RSS, and automatic 301 redirects on slug changes — all with zero manual steps for
  a non-technical author (see `SEO_GUIDE.md`)
- **Real analytics**: per-day view aggregation (never one row per page view), Top Posts,
  search-term tracking — all privacy-conscious, retention-bounded, and toggleable
- **Production-grade infrastructure**: Redis cache with stampede protection and graceful
  failure, Celery + Celery Beat for scheduled publishing and housekeeping, per-request
  tracing, structured JSON logging, health/readiness endpoints
- **Security by default**: CSRF everywhere, sanitized rich content (never `|safe` on
  untrusted input), rate limiting on every abuse-prone endpoint, secure file uploads
  (content-verified, not just extension-checked), audit logging, `check --deploy` clean

## Stack

- Python 3.12, Django 5.1
- PostgreSQL in production, SQLite for local development (same code path via `DATABASE_URL`)
- Redis + Celery + Celery Beat
- Django Templates + Tailwind CSS v4 + Alpine.js (server-rendered, no SPA/build-heavy frontend)
- Quill.js (CDN) for the post editor; `nh3` (Rust, maintained) sanitizes all editor HTML server-side
- Gunicorn + Nginx in production (see `DEPLOYMENT.md`)

## Documentation map

| Doc | For |
|---|---|
| `README.md` (this file) | Overview, install, day-to-day development |
| `ADMIN_GUIDE.md` | Anyone publishing content — no technical background needed |
| `SEO_GUIDE.md` | Writers/editors — what's automatic vs. what you can fine-tune |
| `SECURITY.md` | What's protected, how, and where it lives in the code |
| `DEPLOYMENT.md` | Standing up and operating production infrastructure |
| `DISASTER_RECOVERY.md` | Step-by-step recovery for every major failure mode |
| `.env.example` | Every environment variable, with explanations |

## Project layout

```text
config/
    settings/base|development|production|testing.py
    celery.py               # Celery app; CELERY_BEAT_SCHEDULER uses django-celery-beat's DB scheduler
    urls.py                  # /django-admin/, /admin/, /accounts/, /health/, and apps.public at root

apps/
    accounts/   # custom User model (email login), 5 roles, avatar, auth URLs, login rate limiting
    core/       # health/readiness checks, error handlers, ActivityLog, request-ID + JSON logging,
                # centralized cache service (versioning + stampede protection), housekeeping tasks
    blog/       # Post/Category/Tag/PostRevision/PostImage/PostPreviewToken/PostViewDaily models,
                # sanitizer, services (slugs, reading time, cache keys, search, TOC), analytics,
                # object-level permissions, Celery publishing task
    dashboard/  # the custom Admin Panel: dashboard, posts (+ bulk actions, trash, duplicate),
                # categories, tags (+ merge), users, roles, activity logs, SEO health, redirects,
                # settings (General/SEO/Social/Publishing/Analytics), CSV export, system status
    public/     # the public site: home/blog/post/category/tag/author/search/about/contact/
                # privacy/terms views, token-based preview, RSS feed, sitemap, SEO + JSON-LD
                # helpers, contact form, redirect middleware, search-query analytics

templates/
    admin_panel/    # admin layout, partials, every admin page template
    public/         # public site layout, partials, every public page template
    errors/         # custom 400/403/404/429/500 pages

static/
    css/input.css       # Tailwind source (edit this) — one build serves admin + public
    js/post-editor.js   # Quill setup, autosave, draft recovery, word count, keyboard shortcuts
    js/public-site.js   # copy-code buttons, reading progress, copy-link

deploy/         # gunicorn.conf.py, nginx.conf.example — see DEPLOYMENT.md
media/          # user-uploaded content: avatars, blog/inline/ (in-content images)
requirements/, tests/, package.json
```

## Installation

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements/development.txt

npm install
npm run build   # compiles static/css/input.css -> static/css/app.css
```

Run `npm run watch` while working on templates/CSS to rebuild on save.

## Environment setup

```bash
cp .env.example .env
# edit .env — see .env.example for every variable, with explanations
```

`SECRET_KEY` has no default and must be set. Local development can leave `DATABASE_URL` unset
(falls back to SQLite); if Redis isn't running locally, `CELERY_TASK_ALWAYS_EAGER=True` makes
Celery tasks run inline instead of failing to connect to a broker.

## Database setup

```bash
python manage.py migrate
```

Seeds, via data migrations: five role groups (Super Admin, Admin, Editor, Author,
Contributor), and two Celery Beat `PeriodicTask`s — `publish_scheduled_posts` (every minute)
and `cleanup_old_data` (daily at 03:00). Permissions are attached to roles through the Admin
Panel's Roles screen (`/admin/roles/`), not hard-coded.

## Create an admin user

```bash
python manage.py createsuperuser
python manage.py shell -c "
from django.contrib.auth import get_user_model
from apps.accounts.roles import set_role
u = get_user_model().objects.get(email='you@example.com')
set_role(u, 'Super Admin')
"
```

Login uses **email**, not username.

## Development server

```bash
python manage.py runserver
```

- `/` — the public homepage; `/blog/`, `/category/<slug>/`, `/tag/<slug>/`,
  `/author/<username>/`, `/search/`, `/about/`, `/contact/`, `/privacy-policy/`, `/terms/`,
  `/feed/`, `/sitemap.xml`, `/preview/post/<token>/` — all public, no login required
- `/admin/` — the custom Admin Panel (staff/authors use this day to day) — see `ADMIN_GUIDE.md`
- `/django-admin/` — raw Django admin, superuser-only emergency/debug tool
- `/health/`, `/health/ready/` — liveness/readiness for load balancers and uptime monitors

## The Admin/CMS Panel

See `ADMIN_GUIDE.md` for the full non-technical walkthrough. In brief: a Dashboard with real
(cached, invalidated-on-change) statistics and Top Posts; a distraction-free post editor with
autosave, draft recovery, and an SEO Health checklist; bulk post actions; a soft-delete Trash;
Duplicate; token-based shareable preview links; category/tag management with tag merging;
user/role management with object-level permission enforcement everywhere; an activity log
that's append-only by design; and Settings organized into General/SEO/Social/Publishing/Analytics
tabs so no one page is overwhelming.

## SEO

Fully automated — see `SEO_GUIDE.md` for the writer-facing explanation. Technically: every
page computes its own title/description/canonical/robots through one centralized service
(`apps/public/seo.py`), backed by a fallback chain (explicit value → post excerpt → site
default) so a non-technical author never has to fill in a single SEO field for a post to be
correctly indexed. `django.contrib.sitemaps` (not hand-rolled XML) builds `/sitemap.xml` as an
index over cached, invalidated-on-publish sections; `django.contrib.syndication` builds
`/feed/`. A unified `Redirect` model (with loop/self-redirect/chain-flattening protection)
handles both admin-managed redirects and the ones auto-created when a published post's slug
changes. `/admin/seo/` shows real, database-computed SEO health — never estimated numbers.

## Search

PostgreSQL full-text search (`SearchVector`/`SearchQuery`/`SearchRank`, weighted toward the
title) when the database backend is `postgresql`; an indexed `icontains` fallback on SQLite.
Either path is a single ORM-built query — no raw SQL, no Python loops over posts. Query length
is capped, results are rate-limited, and (opt-in via Settings → Analytics) searched terms are
aggregated for a Top Search Terms view — never stored as unbounded raw-query rows.

## Caching

A centralized cache service (`apps/core/cache.py`) provides versioned key-building
(`blog:v1:...` — bump `CACHE_VERSION` to invalidate everything after a key-shape change in one
step, never a full Redis flush) and stampede protection (`get_or_set_with_lock` — only the
first request past an expired cache key recomputes it; concurrent requests wait briefly or
fall back to computing their own copy, never all hammering the database at once). Per-resource
TTLs are independently configurable via environment variables. Every cache read degrades
gracefully to "go to the database" if Redis is unreachable (`IGNORE_EXCEPTIONS` in production)
— a Redis outage slows the site, it does not break it or expose stale/private data.

## Background jobs (Celery)

```bash
celery -A config worker -l info
celery -A config beat -l info   # required for scheduled publishing to actually fire
```

Two tasks, both idempotent by construction (safe to run twice, safe to retry): scheduled post
publishing (checked every minute) and daily housekeeping (expired sessions, aged analytics
rows, stale 404 logs). Both retry automatically on transient database errors with exponential
backoff, and fail once (never retry forever) on a genuine bug. If Celery is down entirely, the
public site keeps working — only future-dated publishing and background cleanup are delayed,
never lost (see `DISASTER_RECOVERY.md` §4).

## Performance & scale

Built to handle 100,000+ posts without redesign: every listing page paginates (never loads all
posts), category/tag/author listings cache an ordered ID list and paginate that in Python
(bounding both query count and payload size regardless of total post count), admin lists are
indexed and paginated, and dashboard statistics are computed once and cached rather than
recalculated per request. No page's query count scales with the number of posts on it —
verified directly in `tests/test_public_performance.py` (3 vs. 20 posts, same query count).

## Security

See `SECURITY.md` for the full picture: authentication, object-level authorization, CSRF, XSS
(server-side sanitization, never `|safe` on untrusted content), SQL injection (ORM-only, no
raw SQL anywhere), secure file uploads (content-verified, not just extension-checked), rate
limiting, secrets management, HTTPS/HSTS, safe error pages, and append-only audit logging.
`python manage.py check --deploy` currently reports zero warnings.

## Tests

```bash
DJANGO_SETTINGS_MODULE=config.settings.testing python manage.py test tests
```

**412 tests, all passing.** Covers every layer built across all eight steps: authentication,
roles/object-level permissions, the full publishing workflow (draft/schedule/publish/archive/
trash/restore/duplicate), revisions, SEO (metadata fallbacks, JSON-LD validity/escaping,
robots rules), sitemap/RSS publication-rule correctness, redirects (loop/self-redirect
prevention, slug-change automation), search, caching (hit/miss/invalidation/stampede
protection), Celery task idempotency and retry policy, analytics aggregation, rate limiting,
and a battery of security tests (IDOR, CSRF, XSS, privilege escalation, unsafe uploads).

`LocMemCache` is a process-wide singleton that Django's per-test DB rollback does not reset —
`tests/base.py::CacheClearingTestCase` clears it in `setUp()`; most test files import it as
`TestCase` so nothing needed renaming as this grew.

## Static files

```bash
npm run build            # Tailwind: static/css/input.css -> static/css/app.css
python manage.py collectstatic --noinput
```

## Production

See `DEPLOYMENT.md` for the complete walkthrough (server setup, PostgreSQL, Redis, Gunicorn,
Nginx, systemd units, HTTPS, monitoring, backups) and `DISASTER_RECOVERY.md` for what to do
when something breaks. In brief:

- Set `DJANGO_SETTINGS_MODULE=config.settings.production`
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are required and validated at settings-import
  time — the app refuses to start rather than run insecurely-misconfigured
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, and HSTS are all on
  by default
- Cache backend switches to Redis automatically, with graceful-failure and stampede protection
- Run both a Celery worker **and** a Celery Beat process, or scheduled publishing silently
  never fires
- Run `python manage.py check --deploy` before shipping — it currently reports no issues
