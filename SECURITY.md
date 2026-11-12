# Security

What's in place, where it lives, and why. Written for whoever inherits this codebase and
needs to answer "is X actually handled?" without re-auditing from scratch.

## Reporting a vulnerability

Email the maintainer directly rather than opening a public issue. Include the URL/endpoint,
the account role you tested with, and reproduction steps. There is no bug bounty program.

## Authentication

- Custom `User` model (`apps/accounts/models.py`), **email as the login identifier**
  (`USERNAME_FIELD = "email"`); `username` is kept only for the stable public author URL
  (`/author/<username>/`).
- Passwords hashed by Django's own hasher chain (PBKDF2 by default) — never a custom scheme.
- `AUTH_PASSWORD_VALIDATORS` (`config/settings/base.py`) enforce: minimum length (10),
  similarity-to-user-attributes, common-password rejection, and numeric-only rejection.
- Password reset uses Django's built-in token-based flow (`PasswordResetForm`,
  `django.contrib.auth.views`) — never a custom reset-token implementation.
- Login is rate-limited two ways at once (`apps/accounts/views.py`): 20/min per IP and 10/min
  per attempted email, so neither rotating IPs nor hammering one IP to lock out a victim works.
  Password reset requests are rate-limited 5/min per email.
- `status` (`active` / `inactive` / `suspended`, `apps/accounts/models.py`) is the single
  source of truth for account access, kept in sync with Django's `is_active` in `User.save()`
  — a suspended user cannot authenticate, full stop, without a second code path to keep in sync.
- Every login, logout, and failed login attempt is written to the audit trail
  (`apps/accounts/signals.py` → `ActivityLog`) — never with the attempted password.

## Authorization

- Five roles (`apps/accounts/roles.py`): Super Admin, Admin, Editor, Author, Contributor —
  backed by real Django `Group`s and model permissions, editable from `/admin/roles/`. Only a
  genuine `is_superuser` may grant or edit the Super Admin role itself
  (`apps/dashboard/guards.py::ensure_can_assign_role` / `ensure_role_editable`) — otherwise
  anyone with `auth.change_group` could self-promote.
- **Object-level authorization** (`apps/blog/permissions.py`) layered on top of Django's global
  permissions, because `user.has_perm(...)` alone can't express "Author X may edit Author X's
  own drafts but not Author Y's." Every mutating post view (`edit`, `delete`, `publish`,
  `schedule`, `trash`, `restore`, `duplicate`, `preview-link`) checks the *object*, not just the
  permission name — changing `/admin/posts/123/` to `/admin/posts/124/` in the URL bar re-runs
  the same check against post 124, it does not inherit whatever was already checked for 123.
  Verified directly: `tests/test_blog_security.py::IDORTests`, `tests/test_post_trash.py`,
  `tests/test_post_bulk_actions.py::BulkActionObjectLevelSecurityTests`.
- Bulk actions (`apps/dashboard/views/posts.py::post_bulk_action`) re-check every selected post
  individually — a request naming an unauthorized post ID alongside authorized ones skips that
  one post rather than silently acting on it because it rode along in the batch.
- A guard layer (`apps/dashboard/guards.py`) prevents: demoting/suspending/deleting yourself,
  and removing the last active Super Admin from the system entirely.
- Mass-assignment is prevented by explicit form field whitelists everywhere a user submits
  data — `role`, `is_staff`, `is_superuser`, `status`, `published_at`, and `author` are never
  accepted as arbitrary POST fields; they're set by view code after validating the actor's
  permission to set them (see `apps/dashboard/forms.py`, `apps/dashboard/forms_blog.py`).

## CSRF

Django's CSRF middleware is on globally; no view uses `@csrf_exempt`. `CSRF_TRUSTED_ORIGINS`
is required (fails startup, not silently) in production (`config/settings/production.py`) —
needed because `SECURE_PROXY_SSL_HEADER` makes Django believe HTTPS requests arrived over
HTTPS, which changes what CSRF's Origin/Referer check considers same-origin.

## XSS

- Post content goes through server-side sanitization (`apps/blog/sanitizer.py`, built on
  `nh3` — a maintained Rust HTML sanitizer, not a hand-rolled regex denylist) before it is ever
  saved, not just before render — `{{ content|safe }}` in a template is trusted because the
  database value is already safe, not because the template trusts user input.
- Everywhere else user input reaches a template, Django's default auto-escaping does the work —
  search queries, contact form fields, bios, SEO title/description fields are never marked
  `|safe`.
- JSON-LD is the one place structured, non-HTML user text (a post title, an author name) is
  embedded inside a `<script>` tag. `apps.public.seo.safe_json_ld()` escapes `</` in the
  serialized JSON so a title containing `</script><script>...` cannot break out of the tag —
  tested directly (`tests/test_public_seo.py::test_json_ld_escapes_closing_script_tags`).
- Inline post images are validated by both extension allowlist (`jpg/jpeg/png/webp` — no
  `svg`, which is exactly the format most prone to XSS-via-upload) and by actually decoding the
  file with Pillow (`Image.open(...).verify()`) before trusting it — an extension alone doesn't
  prove the bytes are a real image (`apps/dashboard/views/posts.py::post_image_upload`).

## SQL injection

Every query in the codebase goes through the Django ORM — no raw SQL anywhere in application
code. Search (`apps/blog/services.py::search_posts`) uses PostgreSQL's `SearchVector`/
`SearchQuery`/`SearchRank` (parameterized by the ORM) with an `icontains` fallback on SQLite;
both paths are ORM-built, never string-formatted into a query.

## File uploads

Two upload surfaces — inline post images (`PostImage`) and user avatars (`User.avatar`) — both:

- restrict to a small extension allowlist (`jpg`, `jpeg`, `png`, `webp` — no `svg`, `gif` is
  also excluded to avoid animated-GIF payload weight, no executable extension is ever accepted)
- enforce a byte-size ceiling (5MB inline images, 2MB avatars)
- generate a random filename server-side (`uuid4().hex` + validated extension) — the original
  filename is discarded, so it can never be used for a path-traversal or extension-confusion
  attack (`apps/blog/models.py::post_image_upload_path`, `apps/accounts/models.py::avatar_upload_path`)
- for inline images specifically, decode the file with Pillow before accepting it (see XSS
  section) — extension/MIME allowlisting alone doesn't prove the bytes are what they claim

Uploaded media is served from `MEDIA_ROOT` as static content only — see `deploy/nginx.conf.example`
for the Nginx rule that explicitly denies executing anything under `/media/` as a script,
belt-and-suspenders alongside the fact that nothing in this codebase ever `exec`s or imports an
uploaded file.

## Rate limiting

`django-ratelimit` (a maintained, focused package — not a hand-rolled counter) on every
sensitive or abuse-prone endpoint: login, password reset, search, contact form, redirect
CRUD, user creation/role-change/status-change, post publish/schedule/image-upload, and the
token-based preview endpoint. Ordinary article reading is **not** rate-limited — the spec's
own instruction, and good practice: throttle actions that cost the system something or that
an attacker benefits from repeating, not normal traffic.

## Secure preview

`/preview/post/<token>/` (`apps/public/views/preview.py`) — a shareable draft link that needs
no login. The token (`secrets.token_urlsafe(32)`, `apps/blog/models.py::PostPreviewToken`) is
the only thing that grants access: never the post's ID, slug, or a timestamp, none of which are
secret. Expires in 30 minutes. A missing token and an expired token both return an identical
404 — never a distinct "this link expired" message, which would confirm to a guesser that the
token format itself was at least structurally valid. Always `noindex, nofollow`; never linked
from the sitemap, RSS, or any public listing.

## Secrets management

- Every secret (`SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, email credentials) is sourced from
  the environment via `python-decouple` (`config(...)` calls throughout `config/settings/`) —
  never hard-coded. `.env` is gitignored; `.env.example` ships with placeholders only.
- `config/settings/production.py` raises `ImproperlyConfigured` at startup — not a silent
  fallback — if `ALLOWED_HOSTS` or `CSRF_TRUSTED_ORIGINS` is left empty.
- The repository was scanned (`grep` across `.py`/`.html`/`.js`/`.md`) for hard-coded
  `secret_key=`/`password=`/`api_key=`/`private_key=` patterns as part of every step's
  sign-off; the only matches are the explicitly-labeled `testing.py` dev-only key and test
  fixture passwords, neither reachable in production.

## HTTPS & transport security

`config/settings/production.py`: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
`CSRF_COOKIE_SECURE` all default **on**; `SECURE_HSTS_SECONDS=31536000` with subdomains and
preload; `SECURE_PROXY_SSL_HEADER` set to trust `X-Forwarded-Proto` — safe specifically
*because* `deploy/nginx.conf.example` is the thing setting that header, terminating TLS before
Django ever sees the request. See `DEPLOYMENT.md` §12 for the redirect-loop failure mode this
combination avoids if the proxy doesn't cooperate.

## Cookies & sessions

`SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE=Lax`, `CSRF_COOKIE_SAMESITE=Lax`.
Production sessions are cache-backed (Redis) rather than DB-backed, so a Redis outage also
means users get logged out (a deliberate trade — see `DISASTER_RECOVERY.md`'s Redis-failure
section) rather than a stale/split session state. Users can always log out
(`/accounts/logout/`); "log out all sessions" is architecturally straightforward to add later
(rotate the session backend's key or bump a per-user session-version field) but isn't built —
noted here as a known, deliberately-deferred item, not an oversight.

## Safe error pages

Custom 400/403/404/429/500 handlers (`apps/core/views.py`) — a visitor never sees a traceback,
SQL, a filesystem path, or an environment variable, in `DEBUG=False`. The 500 page shows an
opaque per-request reference ID (see **Logging** below) so a user can report "reference
`a1b2c3d4e5f6`" and an operator can grep straight to the real error — without exposing
anything about *why* it failed to the person who hit it.

## Audit logging

`ActivityLog` (`apps/core/models.py`) is **append-only by permission design** — its Django
permissions are `("view",)` only; there is no `change`/`delete` permission for the model at
all, so no role, however privileged short of direct database access, can edit or remove an
entry through the application. Tracks: login/logout/failed-login, every post lifecycle
transition (create/update/publish/schedule/archive/restore/trash/permanently-delete/duplicate),
revision restore, category/tag CRUD and merges, redirect CRUD, user CRUD/role/status changes,
settings changes, CSV exports, and preview-link creation. **Never** logs a password, token, or
session key — `log_activity()`'s own docstring calls this out, and every call site passes a
human-readable description plus small, non-sensitive metadata, never a raw request body.
Retention is a deliberate manual operation (`manage.py prune_activity_logs --older-than-days
N`), never an automatic scheduled deletion — see `DISASTER_RECOVERY.md`/`DEPLOYMENT.md` for
the reasoning.

## Logging (operational, not audit)

Every log line carries a per-request ID (`apps/core/middleware.py::RequestIDMiddleware`,
returned as the `X-Request-ID` response header) so a production incident can be traced from a
user's bug report straight to the exact request in `logs/application.log`. Production emits
one JSON object per line (`apps/core/logging_utils.py::JSONFormatter`); levels stay at
INFO/WARNING/ERROR, never DEBUG, so a busy site doesn't fill disk with noise. Log files rotate
at 5MB × 5 backups (`config/settings/base.py::LOGGING`).

## Automated security verification

Run before every release:

```bash
python manage.py check --deploy
```

Currently reports **zero warnings**. The full test suite includes dedicated security test
files exercising the above end to end: `tests/test_security.py`, `tests/test_blog_security.py`,
`tests/test_dashboard_security.py`, `tests/test_public_security.py`, `tests/test_seo_security.py`,
`tests/test_rate_limiting.py`, `tests/test_post_trash.py`, `tests/test_post_bulk_actions.py`.
