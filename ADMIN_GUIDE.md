# Admin Guide

For anyone publishing on this site — no coding, Django, or SEO knowledge required. Everything
technical (slugs, canonical URLs, sitemaps, caching) happens automatically in the background.

## Logging in

Go to `/accounts/login/` and sign in with your **email address** (not a username) and your
password. Forgot it? Use "Forgot password?" on that page — you'll get a reset email.

If your account is suspended or deactivated, login will be blocked. Contact a Super Admin or
Admin to reactivate it.

## The Dashboard

After logging in you land on `/admin/dashboard/` — a snapshot of the site:

- **Published / Drafts / Scheduled / Archived** — how many posts are in each state
- **Authors / Categories / Tags / Total Views** — overall content stats
- **Recent Posts** — the last few posts touched, with their status
- **Top Posts** — your best-performing content by real view counts (never estimated)
- **Recent Activity** — a live feed of what's happened lately (who published what, when)
- **Quick Actions** — the fastest way to a new post, the post list, categories, tags, users, or settings

## Publishing a post — the whole flow

```
New Post → Write → Category → Tags → Preview → SEO Health → Publish
```

### 1. Start a new post

Click **+ New Post** from the Dashboard or the Posts list. You'll land on a clean editor with
just two things that matter right away: **Title** and **Content**.

### 2. Write

Type your title — a URL-friendly slug is generated automatically as you type (you can edit it
by hand if you want a different one; just don't touch it if you're not sure).

The content area is a normal rich-text editor: headings, bold/italic, lists, quotes, code
blocks, links, and images. As you write, you'll see:

- **Words / Characters / Reading time** — updates live as you type
- **Saving…** — your draft is saved automatically every so often while you write, and again
  right before you leave the page, so you don't lose work. If your browser crashes or you
  accidentally navigate away, reopening the post will offer to **Recover** what you were
  writing, or you can **Discard** it and keep what was last saved to the server.

You don't need to click Save constantly — but the **Save Draft** button (or `Ctrl/Cmd+S`) is
always there if you want to be sure.

### 3. Excerpt (optional)

A short summary shown on listing pages and used as the search-engine description if you don't
set one explicitly under SEO. Leave it blank and the system will fall back sensibly — you
don't have to fill this in for the post to work.

### 4. Category

Pick one from the dropdown, or click **+ Create Category** if the right one doesn't exist yet
— you never have to leave the post editor to do this.

### 5. Tags

Start typing to search existing tags, or type a new one and press Enter to create it on the
fly. Try to reuse an existing tag rather than creating a near-duplicate ("Python" vs "python")
— an Admin can merge duplicates later from **Tags → Merge Tags** if it happens anyway.

### 6. Preview

Click **Preview** to see exactly how the post will look once published — before anyone else
can see it. If you need to share a draft with someone who doesn't have a login (an editor,
a reviewer outside the team), click **Get shareable preview link** on the edit page — it
generates a private link that works for 30 minutes and then stops working. Don't share it
publicly; anyone with the link can view the draft while it's valid.

### 7. SEO Health

Every post editor shows an **SEO Health** panel — not a fake "score out of 100", but a
plain checklist: ✓ what's good, ⚠ what's worth a look. Common things it flags:

- Missing an SEO title or meta description (it'll fall back to your post title/excerpt
  automatically — fixing this is a nice-to-have, not a blocker)
- Content that's quite short
- No internal links to other posts

None of this blocks publishing — they're suggestions, not gates. The one thing that *is*
required is a title and content; everything else the system either fills in sensibly or leaves
as a friendly nudge.

You'll also see a **Google Preview** — a live approximation of how the post might appear in
search results, so you can judge your title/description at a glance.

### 8. Publish or Schedule

- **Publish now** — goes live immediately, appears on the homepage, its category/tag pages,
  the sitemap, and the RSS feed within moments.
- **Schedule…** — pick a future date and time; the post publishes itself automatically at
  that moment (checked every minute by a background job). Until then it stays completely
  invisible to the public — not indexed, not in the sitemap, not in RSS, not listed anywhere.

If you don't see a Publish/Schedule option, you don't currently have permission to publish —
ask an Editor or Admin to publish it for you, or to grant you that permission.

## After publishing

- **Editing a published post** is safe — every past version is kept as a **Revision** (see
  the Revisions link on the edit page), so nothing is ever truly lost even if an edit goes
  wrong. You can view any old revision and restore it; restoring keeps the *current* version
  saved as a revision too, so you can always undo an undo.
- **Changing a published post's slug** (the URL-friendly part) automatically creates a
  redirect from the old URL to the new one — visitors and search engines following an old
  link land on the right page instead of a 404.
- **Duplicate** — need a similar post? Click Duplicate to create a fresh draft copy (a new
  slug, no publish date, starts as a draft) that you can then edit and publish separately.

## Managing content

### Post statuses

| Status | Meaning |
|---|---|
| Draft | Not visible to the public at all |
| Scheduled | Will auto-publish at the set time; invisible until then |
| Published | Live on the site |
| Archived | Taken down but kept — restore it back to Draft any time |

### Trash

Deleting a post moves it to **Trash**, not gone forever. From **Posts → Trash** you can
**Restore** it back, or (Super Admins only) **Delete Permanently** — which really is
permanent, so it's a deliberate, separate confirmation step.

### Bulk actions

On the Posts list, select multiple posts with the checkboxes to Publish, Unpublish, Archive,
Change Category, or Move to Trash all at once. Trashing in bulk always asks for confirmation
first — there's no way to accidentally trash a dozen posts with one misplaced click.

### Categories & Tags

**Categories** (`/admin/categories/`) and **Tags** (`/admin/tags/`) each have their own
management page — create, edit, delete, and see how many posts use each one. Deleting a
category doesn't delete its posts; they just become uncategorized. **Merge Tags** lets you
fold near-duplicate tags into one canonical tag across every post that used them.

### Exporting

Both the Posts list and the Users list have an **Export CSV** button — a spreadsheet snapshot
you can open in Excel/Sheets. Post exports never include full content bodies; user exports
never include passwords.

## Users & Roles

*(Requires the appropriate permission — most Authors/Contributors won't see this section.)*

| Role | Can do |
|---|---|
| **Super Admin** | Everything, including managing other Super Admins and system settings |
| **Admin** | Manage posts, categories, tags, authors, and publishing — not core security settings or other Super Admins |
| **Editor** | Create, edit, review, and publish any post; manage categories/tags — not users |
| **Author** | Create and edit their own posts; publish only if explicitly allowed |
| **Contributor** | Draft their own posts only — never publishes directly |

Create a user from **Users → Create User**, set their role and status there. **Suspended**
users cannot log in at all — suspending is preferred over deleting when someone leaves the
team, since it preserves their post history and authorship.

## Settings

`/admin/settings/` is organized into tabs so no single page is overwhelming:

- **General** — posts per page on public listing pages
- **SEO** — site title/description, default meta description, default social-sharing text,
  canonical domain — see `SEO_GUIDE.md` for what each of these actually does
- **Social** — links to your Facebook/X/LinkedIn/GitHub/YouTube (only ones you fill in are shown)
- **Publishing** — whether Authors can publish directly, whether scheduling is enabled,
  and the words-per-minute used to estimate reading time
- **Analytics** — whether view/search tracking is on, and how long that data is kept

Only Super Admins/Admins with the right permission can change these — everyone else just
sees the effects (e.g., the Publish button appearing or not).

## If something goes wrong

- **"Something went wrong" error page** — this isn't your fault; it's already been logged with
  a reference number. Report that number if you contact support.
- **A button/page you expect isn't there** — it's almost always a permissions thing, not a
  bug. Ask a Super Admin or Admin to check your role.
- **You lost internet/closed the tab mid-write** — reopen the post; if there was unsaved work,
  you'll be offered to recover it.
