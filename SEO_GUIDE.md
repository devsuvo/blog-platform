# SEO Guide

For writers and editors. **You do not need to understand any of the technical terms below to
publish an SEO-friendly article** — the system handles them automatically. This guide exists
for the few fields you *can* optionally fine-tune, and to explain what's already being taken
care of for you.

## The short version

Write a good title, write good content, pick a category, add a few relevant tags, and publish.
That's it — everything below already happens without you touching it.

## What's automatic (you never have to think about this)

- **Slug** (the URL-friendly version of your title) — generated as you type. Editable, but the
  auto-generated one is almost always fine.
- **Canonical URL** — every page declares its one "real" address, so search engines never get
  confused by `?utm_source=...` tracking parameters or pagination creating duplicate-looking
  pages.
- **Robots rules** — published posts are indexable; drafts, scheduled posts, archived posts,
  previews, search results, and the admin panel are automatically marked "don't index this" —
  you cannot accidentally leak an unpublished draft into Google.
- **Open Graph & Twitter/X Card** — when someone shares your post link on social media, a
  clean text preview (title + description) is generated automatically. **There is no featured
  image on this platform, by design** — sharing previews are text-only, and that's intentional,
  not a missing feature.
- **JSON-LD structured data** — machine-readable metadata (article type, author, publish date,
  breadcrumbs) that helps search engines understand the page. Fully automatic; never fabricated
  (no fake ratings or reviews are ever added).
- **Sitemap** (`/sitemap.xml`) — updates itself the moment a post is published, unpublished,
  or its slug changes. You never edit this by hand.
- **RSS feed** (`/feed/`) — always reflects exactly what's currently published, nothing else.
- **Redirects** — if you (or an editor) change a *published* post's slug, a redirect from the
  old URL to the new one is created automatically. Old links and search rankings aren't lost.
- **Reading time** — calculated from your word count automatically.

## What you can optionally fill in

Every one of these has a sensible automatic fallback if you leave it blank — think of them as
fine-tuning, not requirements.

| Field | What it's for | Falls back to |
|---|---|---|
| **SEO Title** | The exact text shown in search results / browser tab | Your post title |
| **Meta Description** | The one/two-line summary shown under your title in search results | Your excerpt, or the site's default |
| **Excerpt** | A short summary for listing pages | Auto-derived from your content start |
| **Canonical URL** | Only needed if this exact content is *also* published somewhere else and you want search engines to credit that other URL instead | This post's own URL |
| **Open Graph title/description** | Override just the social-share text specifically | Your SEO title / meta description |

## The SEO Health checklist

Every post editor shows a live checklist — not a fake numeric score. It checks:

- ✓/⚠ SEO title present and a reasonable length
- ✓/⚠ Meta description present and a reasonable length
- ✓ Clean, readable slug
- ✓ Canonical URL is valid (no unsafe schemes)
- ✓/⚠ Content length (very short posts are flagged, never blocked)
- ✓/⚠ Heading structure (your title is the page's H1 automatically; content should generally
  start from H2 — the checklist tells you if it doesn't)
- ⚠ Internal links (a friendly nudge to link to related posts where relevant — not enforced)

**Nothing here blocks publishing except a missing title or missing content.** Warnings are
suggestions you can act on or ignore.

## Search preview & social preview

The editor shows you two live previews as you type:

- **Google Preview** — an approximation of your search-result listing (title, URL,
  description)
- Your Open Graph/Twitter text is what people will see when the link is shared — no image,
  by design, so the preview is purely about how good your title and description read on their
  own.

## Categories, tags, and internal linking

Search engines (and readers) use your site's structure to understand what a post is about.
Pick the single most accurate category, and a handful of genuinely relevant tags — avoid
tagging everything with everything. Linking to a few related posts from within your content
(where it's genuinely useful to the reader) is one of the few *manual* SEO actions worth doing
— the SEO Health checklist will gently remind you if a longer post has no internal links at all.

## Things that are deliberately NOT part of this system

- **No featured/hero/cover image** anywhere, ever — social previews and article pages are
  text-first by design, not a limitation to work around.
- **No fake SEO score** ("97/100") — those numbers are marketing, not measurement. You get an
  honest checklist instead.
- **No keyword stuffing tools** — write for the reader; a clear, well-structured article is
  what actually helps.

## For editors/admins: the settings behind all this

`/admin/settings/seo/` controls the site-wide defaults every post falls back to when a field is
left blank: site title, site name, default meta description, default robots policy, default
Open Graph text, your X/Twitter handle, and the canonical domain (the one true `https://` URL
of the site — this is what every canonical link, sitemap entry, and structured-data URL is
built from, so it should always match the real production domain).

`/admin/seo/` (SEO Health dashboard, staff-only) shows real, database-computed site-wide
numbers — indexed post count, posts missing a title/description, broken redirects, empty
categories/tags, and potential duplicate slugs. Nothing there is estimated.

`/admin/redirects/` manages URL redirects directly if you ever need to create one by hand
(e.g. an old page that moved outside of a simple slug rename).

`/admin/404-logs/` shows paths people are actually hitting that don't exist — useful for
spotting a broken external link worth fixing with a redirect.
