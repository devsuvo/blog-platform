# Disaster Recovery

Step-by-step recovery procedures for each major failure mode. Read this *before* an incident,
not during one. See `DEPLOYMENT.md` for the normal deployment architecture and
`SECURITY.md`/`ADMIN_GUIDE.md` for related context.

General principle throughout: **diagnose before you act**. Every procedure below starts with a
read-only check. Never run a destructive command (a restore, a restart, a rollback) against
production before confirming what's actually broken.

## Quick reference: what depends on what

```
Public blog reading        → needs: PostgreSQL, (Redis optional — degrades gracefully)
Admin panel / publishing   → needs: PostgreSQL, Redis (sessions are cache-backed in prod)
Scheduled publishing       → needs: PostgreSQL, Redis, Celery worker + beat (delayed, not lost, if down)
Search                     → needs: PostgreSQL only
Contact form               → needs: PostgreSQL, outbound SMTP
```

Losing Redis or Celery degrades the site; it does not take it down. Losing PostgreSQL takes
the site down — it is the one hard dependency everything else is built to tolerate losing.

---

## 1. Server failure (host is unreachable / hardware died)

1. Confirm it's actually the server, not DNS or the network path — check the hosting
   provider's status page and try reaching the host by IP directly.
2. If the host is truly gone: provision a replacement following `DEPLOYMENT.md` §1–2 exactly
   (server requirements, Python). Do not skip steps to save time — a rushed setup is how a
   second incident starts during recovery from the first.
3. Restore the database from the most recent backup (§5 below) onto the new host, or point
   `DATABASE_URL` at an existing managed PostgreSQL instance if the database itself survived.
4. Redeploy the application (`DEPLOYMENT.md` §2–11: clone/pull code, `pip install`,
   `.env`, `migrate`, `collectstatic`, Gunicorn, Celery worker + beat).
5. Update DNS (§6 below) to point at the new host's IP if the IP changed.
6. Verify with the smoke test checklist (§8 below) before announcing recovery.

## 2. Database failure (PostgreSQL down or corrupted)

**Symptom:** `/health/ready/` returns `503` with `"database": false`. Every page that touches
the DB fails; `/health/` (liveness) still returns `200` because the Django process itself is
up — this is the intended distinction between the two endpoints (`DEPLOYMENT.md` §15).

1. Check the database server/service status first — a stopped service or exhausted connection
   pool is far more common than actual corruption.
2. If it's a managed database (RDS, Cloud SQL, etc.), check the provider's own health/incident
   dashboard before assuming application-level blame.
3. If the service is stopped, restart it and re-check `/health/ready/`.
4. If the data itself is corrupted or lost: restore from the latest backup (§5). Accept the
   data-loss window between the last backup and the failure — this is why backup frequency
   (§5) should match how much data you can afford to lose.
5. Once restored, run `python manage.py migrate --check` before serving traffic, to confirm
   the restored schema matches the currently-deployed code version.
6. Warm the caches (`python manage.py rebuild_sitemap`) and spot-check a few pages before
   declaring recovery complete.

**What does NOT need special recovery**: Redis-backed caches are rebuildable from the database
by design — once PostgreSQL is back, caches repopulate themselves on the next request. Nothing
needs to be manually restored in Redis.

## 3. Redis failure (cache/broker down)

**By design, this degrades the site — it does not take it down.**

- **Cache reads**: `django-redis` is configured with `IGNORE_EXCEPTIONS: True`
  (`config/settings/production.py`) — a Redis outage makes every cache read silently look like
  a cache miss, and every read already falls through to PostgreSQL on a miss. Pages get
  slower (no cache), not broken. The outage is still visible: it's logged to the
  `django_redis` logger, not swallowed silently.
- **Sessions**: production sessions are cache-backed (`SESSION_ENGINE = "...backends.cache"`).
  A Redis outage means **logged-in users will be logged out** and cannot log back in until
  Redis is restored — this is a deliberate trade (a stale/split session store would be worse)
  documented in `SECURITY.md`. The public (anonymous) blog is unaffected.
- **Celery**: scheduled publishing and the daily cleanup task cannot run without a broker —
  see §4 below. They queue up delay, they do not fail permanently.

**Recovery steps:**

1. Check the Redis service/instance status.
2. Restart it if stopped. No special data recovery is needed for the *cache* — it is entirely
   rebuildable and holds nothing that isn't also in PostgreSQL.
3. If Redis was also acting as the Celery broker with unacknowledged messages, those in-flight
   task messages may be lost depending on your broker's persistence configuration — this is
   acceptable here because both Celery tasks in this project (`publish_scheduled_posts`,
   `cleanup_old_data`) are idempotent and re-run correctly on the next scheduled tick with no
   duplicate side effects (verified: `tests/test_blog_celery.py::test_running_task_twice_is_idempotent`,
   `tests/test_celery_hardening.py`).
4. Confirm via `/admin/system/` (superuser-only System Status page) that Cache and Celery both
   show healthy again.

## 4. Celery failure (worker or beat process down)

**By design, this delays background work — it does not take the public site down.**

1. Check whether it's the **worker**, **beat**, or both that stopped (`systemctl status` for
   each service — see `DEPLOYMENT.md` §10–11 for the expected unit names).
2. While down:
   - Scheduled posts whose time has passed simply wait — they publish as soon as the worker
     and beat are both back, with no duplicate-publish risk (idempotent by construction: the
     publish task's UPDATE re-checks `status=SCHEDULED`, so a delayed/redelivered run that
     finds the post already published updates zero rows).
   - The daily cleanup task (stale 404 logs, aged analytics rows) simply runs late.
   - Nothing about reading or publishing a post *manually* through the admin panel depends on
     Celery — only *scheduled* (future-dated) publishing does.
3. Restart the stopped service(s).
4. Confirm recovery: check `/admin/system/` for the periodic task list — `last_run_at` should
   start advancing again, and any overdue scheduled posts should publish within one minute
   (the `publish_scheduled_posts` beat interval).
5. Run `python manage.py cleanup_old_data` manually if the daily job was missed for an
   extended period and you don't want to wait for the next scheduled run.

## 5. Backup restoration

**Backup strategy** (see also `DEPLOYMENT.md` §13):

| Tier | Frequency | Retention |
|---|---|---|
| Daily | Every day | 30 days |
| Weekly | Every Sunday | 12 weeks |
| Monthly | 1st of the month | 12 months |

Prefer your hosting provider's managed backup/snapshot feature (RDS automated backups + PITR,
Cloud SQL automated backups, etc.) over a hand-rolled `pg_dump` cron job where available —
less to maintain, and typically supports point-in-time recovery a manual dump doesn't.

**What's backed up:** PostgreSQL (the only durable state — see the dependency table above) and
the `media/` directory (user-uploaded inline images and avatars). Redis is deliberately **not**
backed up — see §3.

**Restore procedure** (practice this in staging before you ever need it for real):

1. Provision or point at a fresh PostgreSQL instance — never restore over a production
   database that might still hold salvageable data without first taking a "before" snapshot
   of its current (broken) state, in case the backup turns out to be the wrong one.
2. Restore the dump: `pg_restore` (custom-format dumps) or `psql < backup.sql` (plain SQL).
3. Restore `media/` from the same point-in-time backup.
4. Point `DATABASE_URL` at the restored database.
5. `python manage.py migrate --check` — confirm the restored schema matches the deployed code
   before serving any traffic from it.
6. **Verify the data actually came back**, specifically:
   - [ ] Posts — spot-check a few known posts exist with correct content/status
   - [ ] Users — log in as a known account; confirm roles are intact
   - [ ] Categories & Tags — confirm counts look right, no orphaned relations
   - [ ] Settings — `/admin/settings/` reflects the expected site name/SEO defaults, not blank
     defaults from a fresh `SiteSetting` row
7. `python manage.py rebuild_sitemap` to warm the sitemap cache against the restored data.
8. Run the smoke test (§8) before announcing the restore is complete.

**Never test restoration against production** — restore into a separate staging database, or
a clone, even when practicing.

## 6. DNS / domain issues

1. Confirm the actual DNS records currently resolving (`dig example.com`, `dig www.example.com`)
   against what's expected: an `A` record (and `AAAA` if IPv6 is used) for the root domain, and
   either an `A`/`AAAA` or `CNAME` for `www`.
2. If records are wrong or missing, correct them at the DNS provider. Propagation can take
   up to the record's TTL — don't panic-repeat changes within that window.
3. Confirm `SITE_URL` (environment variable, drives canonical URLs, sitemap, OG/JSON-LD — see
   `config/settings/base.py`) and `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` still match the real
   domain. A domain change that isn't reflected in these three settings will produce a working
   site with silently wrong canonical URLs, or CSRF failures on every form submission.

## 7. SSL / certificate issues

1. Check certificate validity and expiry: `openssl s_client -connect example.com:443 -servername example.com`.
2. If using Let's Encrypt/certbot (referenced in `deploy/nginx.conf.example`), confirm the
   renewal timer/cron is actually running (`certbot renew --dry-run`) — most SSL incidents are
   a silently-failed auto-renewal, not a new problem.
3. After renewing, reload (not necessarily restart) Nginx to pick up the new certificate files.
4. Verify no mixed-content warnings — everything on this site is served same-origin
   (static/media through the same Nginx host), so this is rarely an issue unless `SITE_URL`
   or `canonical_domain` (SEO settings) points at `http://` instead of `https://`.

## 8. Post-recovery smoke test

Run this after *any* recovery procedure above, before considering the incident closed:

1. Homepage loads (`/`)
2. `/health/` returns `200`
3. `/health/ready/` returns `200` with both `database` and `cache` `true`
4. Log in to the admin panel
5. Create a test post, publish it
6. View the published post on the public site
7. `/search/` returns results
8. `/sitemap.xml` includes the test post
9. `/feed/` includes the test post
10. Log out cleanly
11. Delete the test post (or move it to trash) so it doesn't linger as noise

If every step above passes, the incident is resolved.
