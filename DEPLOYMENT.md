# Deployment

Production architecture:

```
Internet
   │
 Nginx  ── serves /static/, /media/ directly; terminates HTTPS; proxies everything else
   │
Gunicorn (config.wsgi:application, deploy/gunicorn.conf.py)
   │
 Django ── config/settings/production.py
   │
PostgreSQL                    Redis
                                ├── Django cache (django-redis, IGNORE_EXCEPTIONS on)
                                └── Celery broker + result backend

Celery Worker   ── apps/blog/tasks.py, apps/core/tasks.py
Celery Beat     ── django-celery-beat DatabaseScheduler (schedule lives in the DB, not code)
```

Keep this simple: one Postgres, one Redis, one (or a few, load-balanced) Gunicorn instance(s),
one Celery worker, one Celery Beat. Nothing here requires container orchestration to run
correctly — add that later if actual scale requires it, not preemptively.

## 1. Server requirements

- Linux host (any modern distro), 1+ CPU core, 1GB+ RAM as a floor for a low-traffic site
- Outbound network access for email (SMTP) and, if used, an external error-monitoring service
- A domain with DNS pointed at the host, and a way to issue a TLS certificate (Let's Encrypt/certbot works fine)

## 2. Python

Python 3.12 (matches local development — see `README.md`).

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements/production.txt
```

`requirements/production.txt` pulls in `requirements/base.txt` plus `gunicorn`. Nothing in
`requirements/development.txt` (which is dev-only) belongs on a production host.

## 3. PostgreSQL

Create a database and user, then point `DATABASE_URL` at it:

```
DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/blog
```

`config/settings/base.py` parses this via `dj-database-url` with `CONN_MAX_AGE=600` (persistent
connections, reused for 10 minutes instead of reopened per request) and `CONN_HEALTH_CHECKS=True`
(a pooled/proxied connection — e.g. behind PgBouncer — that's gone stale gets transparently
replaced instead of raising on the next request). Routine `VACUUM`/`ANALYZE` maintenance is left
to PostgreSQL's own autovacuum — do not script destructive maintenance from Django.

## 4. Redis

One Redis instance, used for both the Django cache and the Celery broker/result backend (see
`REDIS_URL` in `.env.example` — `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` default to the same
URL but can point elsewhere if you want the queue on a separate instance). Redis persistence
(RDB/AOF) is optional here: every cache key is rebuildable from PostgreSQL on a miss, and Celery
Beat's schedule itself lives in Postgres (django-celery-beat), not Redis — losing Redis loses
in-flight tasks and warm caches, not durable state.

Production's cache backend sets `IGNORE_EXCEPTIONS: True` (see `config/settings/production.py`):
if Redis is briefly unreachable, cache reads degrade to "always a miss" (falls through to
PostgreSQL) rather than turning into a 500 on every page. This is logged via the
`django_redis` logger, not silent.

## 5. Environment variables

Copy `.env.example` to `.env` on the server and fill in real values — see that file for the
full list with descriptions. Never commit `.env`. At minimum, production needs:

`SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `DATABASE_URL`,
`REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `EMAIL_*`.

`config/settings/production.py` raises `ImproperlyConfigured` at startup (not a silent fallback)
if `ALLOWED_HOSTS` or `CSRF_TRUSTED_ORIGINS` is left empty — a missing production secret fails
loudly before serving a single request, not quietly with a broken CSRF/host check.

## 6. Migrations

```bash
DJANGO_SETTINGS_MODULE=config.settings.production python manage.py migrate
```

Run this on every deploy, before restarting Gunicorn/Celery, as part of your deploy script —
not manually, not skipped "because nothing changed" (a missed migration is a silent bug).

## 7. Static files

```bash
DJANGO_SETTINGS_MODULE=config.settings.production python manage.py collectstatic --noinput
```

Collects into `STATIC_ROOT` (`staticfiles/`), which Nginx serves directly from
(`deploy/nginx.conf.example`) — Gunicorn/Django never handles a static file request in
production. Run `npm run build` first if `static/css/input.css` changed, so `collectstatic`
picks up the current compiled `app.css`.

## 8. Gunicorn

```bash
gunicorn config.wsgi:application -c deploy/gunicorn.conf.py
```

See `deploy/gunicorn.conf.py` for worker count/timeout/logging, all overridable via
`GUNICORN_*` env vars — the file documents the reasoning for each default (worker count is a
starting point based on CPU cores, not a fixed number; measure and adjust under real traffic).
Never run `manage.py runserver` in production — it's single-threaded, unauthenticated-static-file
tooling, not a production server.

Run it under a process supervisor (systemd unit, Supervisor, or your platform's process
manager) so it restarts on crash and starts on boot. A minimal systemd unit:

```ini
# /etc/systemd/system/gunicorn-blog.service
[Unit]
Description=Gunicorn — Blog Platform
After=network.target

[Service]
User=www-data
WorkingDirectory=/srv/blog-platform
EnvironmentFile=/srv/blog-platform/.env
ExecStart=/srv/blog-platform/venv/bin/gunicorn config.wsgi:application -c deploy/gunicorn.conf.py --bind unix:/run/gunicorn-blog.sock
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 9. Nginx / reverse proxy

See `deploy/nginx.conf.example` — HTTPS termination, static/media served directly, everything
else proxied to Gunicorn over a Unix socket, `X-Forwarded-Proto` set (required — see §12), and
explicit `deny` rules for `.env`/`.git` and for executing anything under `/media/` as a script.

## 10. Celery worker

```bash
celery -A config worker --loglevel=info
```

Run under the same process supervisor as Gunicorn. If the worker is down, the public site keeps
working — nothing in the request path (`apps/public/`) depends on Celery being reachable; only
scheduled publishing and the daily cleanup job are delayed until it's back up (see
`DISASTER_RECOVERY.md` §4 — by design, not an oversight).

```ini
# /etc/systemd/system/celery-worker-blog.service
[Unit]
Description=Celery Worker — Blog Platform
After=network.target redis.service

[Service]
User=www-data
WorkingDirectory=/srv/blog-platform
EnvironmentFile=/srv/blog-platform/.env
ExecStart=/srv/blog-platform/venv/bin/celery -A config worker --loglevel=info
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## 11. Celery Beat

```bash
celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

The schedule lives in PostgreSQL (`django_celery_beat` tables), seeded by data migrations
(`apps/blog/migrations/0002_seed_scheduled_publishing_task.py` — every 1 minute, checks for due
scheduled posts; `apps/core/migrations/0004_seed_cleanup_old_data_task.py` — daily at 03:00,
housekeeping). Editable afterward from Django admin (`/django-admin/django_celery_beat/`) without
a code change or redeploy. Run exactly one Beat process — two would double-schedule every task.

```ini
# /etc/systemd/system/celery-beat-blog.service
[Unit]
Description=Celery Beat — Blog Platform
After=network.target redis.service postgresql.service

[Service]
User=www-data
WorkingDirectory=/srv/blog-platform
EnvironmentFile=/srv/blog-platform/.env
ExecStart=/srv/blog-platform/venv/bin/celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

All three units (Gunicorn, worker, Beat) share the pattern: `Restart=on-failure` so a crash
self-heals, `WantedBy=multi-user.target` so they start on boot, and stdout/stderr captured by
systemd/journald automatically — nothing extra needed for basic log capture.

## 12. HTTPS

`SECURE_SSL_REDIRECT=True` and `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`
are set in `config/settings/production.py`. This combination only works — and only avoids a
redirect loop — because Nginx sets `X-Forwarded-Proto: https` on every request it proxies (see
`deploy/nginx.conf.example`). If you front this with a different proxy/load balancer, confirm it
sets that same header, or `SECURE_SSL_REDIRECT` will loop.

`SITE_URL` (canonical domain, used for SEO/canonical/OG/JSON-LD — see Step 5) must be the real
`https://` production domain.

## 13. Backup strategy

Documented here, not automated from Django — a script with delete/overwrite permissions has no
business running inside the same app as the data it's protecting.

- **What**: PostgreSQL (the only durable state — Redis is rebuildable, see §4) and the `media/`
  directory (user-uploaded inline images).
- **Frequency**: daily full backup at minimum (`pg_dump`), more often if publish volume justifies
  it. Most managed Postgres hosts (RDS, Cloud SQL, etc.) offer automated daily snapshots plus
  point-in-time recovery — prefer that over a hand-rolled cron job where available.
- **Retention**: 30 days of daily backups is a reasonable default; keep longer if compliance
  requires it. Store off the application host (a separate bucket/region), never only alongside
  the database it's backing up.
- **Restore procedure**: practice it before you need it.
  1. Provision/point a fresh PostgreSQL instance.
  2. `pg_restore` (or `psql < backup.sql`) the latest backup.
  3. Restore the `media/` directory from the same point in time.
  4. Point `DATABASE_URL` at the restored database, run `python manage.py migrate --check` to
     confirm the schema matches the current codebase before serving traffic.
  5. Warm the cache (`python manage.py rebuild_sitemap`) and spot-check a few pages.

## 14. Logs

- `logs/application.log`, `logs/security.log` — rotating file handlers (5MB × 5 backups), written
  by the app itself regardless of where Gunicorn's own stdout/stderr goes.
- Gunicorn's `accesslog`/`errorlog` go to stdout/stderr (`deploy/gunicorn.conf.py`) — capture
  that with your process supervisor (`journalctl -u gunicorn-blog`, Docker's log driver, etc.).
- Production log lines are one JSON object each (`apps/core/logging_utils.JSONFormatter`) —
  `{"timestamp", "level", "module", "request_id", "message", ...}` — parseable by any log
  aggregator without a vendor-specific shipper config. Every line from a given request carries
  the same `request_id`, which is also returned as the `X-Request-ID` response header and shown
  (as an opaque reference, nothing sensitive) on the custom 500 page — grep production logs for
  the ID a user reports to find exactly what happened.
- Levels stay at INFO/WARNING/ERROR in production — never DEBUG (see `LOGGING` in
  `config/settings/base.py`); a busy site logging every DEBUG line would fill disk fast for no
  operational benefit.

## 15. Health checks

- `GET /health/` — liveness. Always `200 {"status": "ok"}` if the process is up; reports nothing
  about DB/cache so it can't leak infrastructure state to an unauthenticated caller. Point an
  uptime monitor or your orchestrator's liveness probe here.
- `GET /health/ready/` — readiness. Pings PostgreSQL (`SELECT 1`) and Redis (a cache
  set/get round trip); `200 {"status": "ready", "database": true, "cache": true}` or
  `503 {"status": "unavailable", ...}`. Booleans only — no hostname, port, or credential in the
  response. Point a load balancer's readiness probe here so it stops routing traffic to an
  instance that can't actually serve a request, without restarting the process outright.
- `/admin/system/` — authenticated (superuser-only) system status page: Django/Python versions,
  DB/cache/Celery status, and the Celery Beat periodic task list (last run, enabled/disabled) —
  a human-facing complement to the two machine-facing endpoints above, not a replacement for
  proper monitoring/alerting.

## 16. Monitoring

Lightweight, not overengineered — this is a content site, not a payments platform:

- **Uptime**: point any external uptime checker (UptimeRobot, Better Uptime, a cron'd curl —
  whatever you already use) at `/health/` on an interval (1–5 min). Alert on non-200.
- **Readiness**: same tool, or your orchestrator's readiness probe, against `/health/ready/` —
  distinguishes "process is up but can't serve" from "process is down."
- **Application errors**: `logs/application.log` (JSON lines in production) is the source of
  truth. Point a log shipper (Vector, Filebeat, or your platform's built-in log drain) at it,
  or at minimum alert on `"level":"ERROR"` frequency crossing a threshold.
- **Host resources** (CPU/RAM/disk): most hosting providers expose this natively (a cloud
  console graph, `htop`/`df -h` over SSH for a single small server). A dedicated metrics stack
  (Prometheus/Grafana) is worth adding once traffic or team size justifies the operational
  cost — not a day-one requirement for this project's scale.
- **PostgreSQL / Redis**: managed database/cache providers expose their own dashboards
  (connections, memory, replication lag). For self-hosted, `pg_stat_activity` and `redis-cli
  INFO` cover the basics manually.
- **Celery**: `/admin/system/` (superuser-only) shows worker eager-mode status and every
  periodic task's `last_run_at`/`total_run_count`/enabled state — a stalled `last_run_at` on
  `publish_scheduled_posts` (should advance every ~1 minute) is the single most useful signal
  that the worker or Beat has quietly died.
- **Error monitoring service** (Sentry or similar): not wired in by default — the JSON
  structured logging (§14) is deliberately vendor-neutral so one can be added later by pointing
  its client at the same log stream, without an application code change forced by a vendor choice.

## 17. Log rotation & retention

- `logs/application.log` and `logs/security.log` rotate automatically at 5MB, keeping 5 backups
  each (`RotatingFileHandler`, `config/settings/base.py::LOGGING`) — roughly 25MB ceiling per
  log file, self-managing, no external `logrotate` config required for these two files.
- Gunicorn/Celery output goes to systemd/journald (§8/§10/§11) — configure journald's own
  retention (`/etc/systemd/journald.conf`, `SystemMaxUse=`) if disk space for journal logs
  becomes a concern; this is a systemd-level setting, not an application one.
- **Retention policy**: keep 90 days of detailed application logs (matches the rotation math
  above at typical traffic; adjust backup count if actual log volume differs). `ActivityLog`
  (the audit trail, a database table, not a log file) is retained indefinitely by default and
  pruned only via the explicit, manual `manage.py prune_activity_logs --older-than-days N`
  command — never automatically. A reasonable audit retention policy is 2 years
  (`--older-than-days 730`) unless compliance requirements dictate otherwise; run it as a
  deliberate, occasional operator action, not a cron job.

## 18. Disk space

Things that grow over time and are worth a threshold alert (e.g. 80% full) rather than waiting
for 100%:

| What | Grows from | Managed by |
|---|---|---|
| `media/` | Inline post images, avatars | Nothing automatic — monitor manually; there's no built-in cap on total media size |
| `logs/` | Application/security logs | Self-capped at ~25MB each via rotation (§17) |
| Database storage | Posts, revisions, activity log, analytics | See §19 |
| Backups | Daily/weekly/monthly snapshots | Your backup tool's retention policy (`DISASTER_RECOVERY.md` §5) |

A simple `df -h` threshold alert on the host (most providers offer this natively) is sufficient
at this project's scale — a dedicated disk-monitoring agent is more than this needs on day one.

## 19. Database storage & retention

The tables most likely to grow unbounded, and what bounds each:

- **Posts/Revisions** — revisions are capped at 20 per post (`REVISION_CAP`,
  `apps/dashboard/views/posts.py`); older revisions are pruned automatically as new ones are
  created. Posts themselves are bounded only by actual content volume — the architecture
  (indexed queries, cached ID-list pagination) is built to handle 100,000+ posts without
  degrading (see `apps/blog/services.py::get_category_post_ids` and friends).
- **ActivityLog** — unbounded by default (it's an audit trail); see §17's retention guidance.
- **PostViewDaily / SearchQueryStat** (analytics) — aggregated, never one row per raw event.
  Pruned automatically by the daily `cleanup_old_data` Celery task according to
  `SiteSetting.analytics_retention_days` (Settings → Analytics, default ~13 months).
- **NotFoundLog** — pruned automatically by the same daily task (entries not seen in 90+ days).

---

## Final verification commands

Run before every production deploy:

```bash
python manage.py check
python manage.py check --deploy
python manage.py test
python manage.py collectstatic --noinput
```

Then confirm the four long-running processes are actually up: Gunicorn, Celery worker, Celery
Beat, and that Redis/PostgreSQL are reachable (`/health/ready/` covers the latter two in one call).
