import re
import unicodedata

from django.conf import settings
from django.core.cache import cache
from django.utils.html import strip_tags

from apps.core.cache import get_or_set_with_lock, make_key

_WHITESPACE_RE = re.compile(r"\s+")
_SEPARATOR_RE = re.compile(r"[-\s_]+")
_HEADING_RE = re.compile(r"<h([23])>(.*?)</h\1>", re.DOTALL | re.IGNORECASE)
PUBLIC_CACHE_TTL = 300  # legacy fallback default; call sites now prefer the settings.CACHE_TTL_* values below


def plain_text_word_count(html_content):
    if not html_content:
        return 0
    text = strip_tags(html_content)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return len(text.split(" ")) if text else 0


def unicode_slugify(value):
    """Like `django.utils.text.slugify(allow_unicode=True)`, but keeps
    combining marks (Unicode categories Mn/Mc) instead of stripping them.

    Django's own slugify drops those, which mangles any script that
    composes letters with combining vowel signs — Bangla ("সালের"
    -> "সলর"), Devanagari, Thai, etc. Keeping them is what makes
    "২০২৬ সালের সেরা ডিজিটাল মার্কেটিং ট্রেন্ড" produce a readable slug
    instead of a garbled one.
    """
    value = unicodedata.normalize("NFKC", str(value)).lower().strip()
    kept = [
        ch for ch in value
        if ch.isalnum() or ch in " -_" or unicodedata.category(ch) in ("Mn", "Mc")
    ]
    value = _SEPARATOR_RE.sub("-", "".join(kept))
    return value.strip("-")


def generate_unique_slug(model_cls, title, instance_pk=None):
    """Slugify `title` (Unicode-preserving, so Bangla and English titles
    both produce readable, SEO-friendly slugs) and disambiguate collisions
    with a numeric suffix.
    """
    base_slug = unicode_slugify(title) or "post"
    slug = base_slug
    suffix = 2
    queryset = model_cls.objects.all()
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)
    while queryset.filter(slug=slug).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


# ---------------------------------------------------------------------------
# Cache keys — public-facing views (Step 4) read through these same keys, so
# invalidation here is what keeps them correct once that layer exists.
# ---------------------------------------------------------------------------
def post_detail_cache_key(slug):
    return make_key("post", "slug", slug)


def latest_posts_cache_key():
    return make_key("homepage", "latest-posts")


def category_posts_cache_key(category_slug):
    return make_key("category", category_slug, "posts")


def tag_posts_cache_key(tag_slug):
    return make_key("tag", tag_slug, "posts")


def author_posts_cache_key(username):
    return make_key("author", username)


def popular_posts_cache_key():
    return make_key("homepage", "popular-posts")


def category_summary_cache_key():
    return make_key("category-summary")


def featured_posts_cache_key():
    return make_key("homepage", "featured-posts")


def published_count_cache_key():
    return make_key("published-post-count")


def rss_feed_cache_key():
    return make_key("rss", "latest")


SITEMAP_SECTIONS = ["index", "posts", "categories", "tags", "authors", "static"]


def sitemap_cache_key(section):
    return make_key("sitemap", section)


def invalidate_sitemap_cache():
    """A post/category/tag change could add, remove, or re-date a URL in
    any section (and always changes the index's own lastmod), so every
    section is invalidated together — sitemaps are cheap to regenerate
    and infrequently requested compared to public pages, so this isn't
    the "never flush everything" cache the rest of the app is careful
    about; it's a handful of specific, named keys, not a full flush.
    """
    cache.delete_many([sitemap_cache_key(section) for section in SITEMAP_SECTIONS])


def invalidate_post_caches(post, previous_slug=None):
    """Delete only the cache keys a change to this post could affect —
    never a full cache flush.
    """
    keys = {
        latest_posts_cache_key(),
        popular_posts_cache_key(),
        category_summary_cache_key(),
        featured_posts_cache_key(),
        published_count_cache_key(),
        post_detail_cache_key(post.slug),
        rss_feed_cache_key(),
    }
    if previous_slug and previous_slug != post.slug:
        keys.add(post_detail_cache_key(previous_slug))
    if post.category_id:
        keys.add(category_posts_cache_key(post.category.slug))
    for tag in post.tags.all():
        keys.add(tag_posts_cache_key(tag.slug))
    keys.add(author_posts_cache_key(post.author.username))
    cache.delete_many(list(keys))
    invalidate_sitemap_cache()


def invalidate_category_caches(category):
    keys = [category_summary_cache_key()]
    if category.slug:
        keys.append(category_posts_cache_key(category.slug))
    cache.delete_many(keys)
    invalidate_sitemap_cache()


def invalidate_tag_caches(tag):
    keys = []
    if tag.slug:
        keys.append(tag_posts_cache_key(tag.slug))
    if keys:
        cache.delete_many(keys)
    invalidate_sitemap_cache()


# ---------------------------------------------------------------------------
# Public querysets — every public-facing view funnels through these so
# "published" has exactly one definition and drafts/scheduled/archived posts
# can never leak through a listing or search result.
# ---------------------------------------------------------------------------
def published_posts_queryset():
    from django.utils import timezone

    from .models import PostStatus

    return _post_base_queryset().filter(
        status=PostStatus.PUBLISHED, published_at__lte=timezone.now()
    )


def _post_base_queryset():
    from .models import Post

    # deleted_at__isnull=True here is the single choke point that keeps a
    # trashed post out of every public page, search, sitemap, and feed —
    # every one of those already funnels through this function or
    # `published_posts_queryset()`.
    return Post.objects.select_related("author", "category").filter(deleted_at__isnull=True)



def _hydrate_posts(post_ids, select_related=("author", "category"), prefetch_related=()):
    """Turn a cached list of PKs back into real Post instances, in the
    same order — `filter(pk__in=...)` does not preserve that order, and
    every cached-ID-list function here relies on it already being the
    right order (most-recent-first, highest-viewed-first, ...).
    """
    from .models import Post

    queryset = Post.objects.filter(pk__in=post_ids)
    if select_related:
        queryset = queryset.select_related(*select_related)
    if prefetch_related:
        queryset = queryset.prefetch_related(*prefetch_related)
    by_id = {post.pk: post for post in queryset}
    return [by_id[pk] for pk in post_ids if pk in by_id]


def get_latest_posts(limit=6):
    ttl = getattr(settings, "CACHE_TTL_HOMEPAGE", PUBLIC_CACHE_TTL)
    post_ids = get_or_set_with_lock(
        latest_posts_cache_key(),
        lambda: list(
            published_posts_queryset().order_by("-published_at")[:limit].values_list("pk", flat=True)
        ),
        ttl,
    )
    return _hydrate_posts(post_ids, prefetch_related=("tags",))


def get_popular_posts(limit=5):
    ttl = getattr(settings, "CACHE_TTL_HOMEPAGE", PUBLIC_CACHE_TTL)
    post_ids = get_or_set_with_lock(
        popular_posts_cache_key(),
        lambda: list(
            published_posts_queryset().order_by("-views_count", "-published_at")[:limit]
            .values_list("pk", flat=True)
        ),
        ttl,
    )
    return _hydrate_posts(post_ids)


def get_category_summary():
    """Categories that have at least one published post, with counts —
    used by the homepage and the header's Categories menu.
    """
    from django.db.models import Count, Q

    from .models import Category, PostStatus
    from django.utils import timezone

    def build():
        return list(
            Category.objects.annotate(
                published_count=Count(
                    "posts",
                    filter=Q(posts__status=PostStatus.PUBLISHED, posts__published_at__lte=timezone.now()),
                )
            )
            .filter(published_count__gt=0)
            .order_by("name")
            .values("name", "slug", "description", "published_count")
        )

    ttl = getattr(settings, "CACHE_TTL_LISTING", PUBLIC_CACHE_TTL)
    return get_or_set_with_lock(category_summary_cache_key(), build, ttl)


def get_featured_posts(limit=4):
    """Editorially-picked posts (`Post.is_featured`) for the homepage's
    "Start Here" section, backfilled with the latest published posts when
    fewer than `limit` are marked featured — a small site with no featured
    posts set yet still gets a sensible, non-empty section.
    """
    ttl = getattr(settings, "CACHE_TTL_HOMEPAGE", PUBLIC_CACHE_TTL)

    def build():
        featured_ids = list(
            published_posts_queryset().filter(is_featured=True)
            .order_by("-published_at")[:limit].values_list("pk", flat=True)
        )
        if len(featured_ids) < limit:
            backfill = list(
                published_posts_queryset().exclude(pk__in=featured_ids)
                .order_by("-published_at")[: limit - len(featured_ids)]
                .values_list("pk", flat=True)
            )
            featured_ids += backfill
        return featured_ids

    post_ids = get_or_set_with_lock(featured_posts_cache_key(), build, ttl)
    return _hydrate_posts(post_ids)


def get_published_post_count():
    ttl = getattr(settings, "CACHE_TTL_LISTING", PUBLIC_CACHE_TTL)
    return get_or_set_with_lock(published_count_cache_key(), published_posts_queryset().count, ttl)


def get_category_post_ids(category):
    """Full ordered list of a category's published post PKs — cached and
    paginated in Python (see `paginate_post_ids`) rather than re-querying
    with COUNT + OFFSET on every page view. At 100k+ posts a popular
    category is still a small list of ints, cheap to cache and slice.
    """
    ttl = getattr(settings, "CACHE_TTL_LISTING", PUBLIC_CACHE_TTL)
    return get_or_set_with_lock(
        category_posts_cache_key(category.slug),
        lambda: list(
            published_posts_queryset().filter(category=category)
            .order_by("-published_at").values_list("pk", flat=True)
        ),
        ttl,
    )


def get_tag_post_ids(tag):
    ttl = getattr(settings, "CACHE_TTL_LISTING", PUBLIC_CACHE_TTL)
    return get_or_set_with_lock(
        tag_posts_cache_key(tag.slug),
        lambda: list(
            published_posts_queryset().filter(tags=tag)
            .order_by("-published_at").values_list("pk", flat=True)
        ),
        ttl,
    )


def get_author_post_ids(author):
    ttl = getattr(settings, "CACHE_TTL_LISTING", PUBLIC_CACHE_TTL)
    return get_or_set_with_lock(
        author_posts_cache_key(author.username),
        lambda: list(
            published_posts_queryset().filter(author=author)
            .order_by("-published_at").values_list("pk", flat=True)
        ),
        ttl,
    )


def paginate_post_ids(post_ids, page_number, page_size):
    """Slice a cached list of PKs into a real Django `Page` of hydrated
    Post instances — the pagination itself is pure-Python (no query), only
    the page's own rows hit the database.
    """
    from django.core.paginator import Paginator

    paginator = Paginator(post_ids, page_size)
    page_obj = paginator.get_page(page_number)
    page_obj.object_list = _hydrate_posts(list(page_obj.object_list), prefetch_related=("tags",))
    return page_obj


def search_posts(query):
    """Search title/excerpt/content/category/tags, published posts only.

    Uses PostgreSQL full-text search when available (ranked, weighted
    toward the title); falls back to indexed `icontains` on SQLite. Either
    way this is a single ORM-built query — no Python-side loops over posts,
    no raw SQL, so it's not an injection vector.
    """
    from django.db import connection
    from django.db.models import Q

    query = (query or "").strip()[:200]
    if not query:
        return published_posts_queryset().none()

    base = published_posts_queryset().prefetch_related("tags")

    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

        vector = (
            SearchVector("title", weight="A")
            + SearchVector("excerpt", weight="B")
            + SearchVector("content", weight="C")
        )
        search_query = SearchQuery(query)
        return (
            base.annotate(rank=SearchRank(vector, search_query))
            .filter(rank__gte=0.01)
            .order_by("-rank", "-published_at")
            .distinct()
        )

    return (
        base.filter(
            Q(title__icontains=query)
            | Q(excerpt__icontains=query)
            | Q(content__icontains=query)
            | Q(category__name__icontains=query)
            | Q(tags__name__icontains=query)
        )
        .order_by("-published_at")
        .distinct()
    )


def inject_heading_ids_and_get_toc(html):
    """Give every <h2>/<h3> in sanitized post content a stable, unique
    anchor id and return a (level, id, text) outline alongside the
    rewritten HTML — server-rendered so the Table of Contents works
    without JavaScript and search engines see real anchor links.
    """
    if not html:
        return html, []

    toc = []
    used_ids = set()

    def repl(match):
        level = int(match.group(1))
        inner = match.group(2)
        text = strip_tags(inner).strip()
        base_id = unicode_slugify(text) or f"section-{len(toc) + 1}"
        heading_id = base_id
        suffix = 2
        while heading_id in used_ids:
            heading_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(heading_id)
        toc.append({"level": level, "id": heading_id, "text": text})
        return f'<h{level} id="{heading_id}">{inner}</h{level}>'

    new_html = _HEADING_RE.sub(repl, html)
    return new_html, toc


_INTERNAL_LINK_RE = re.compile(r'<a\s[^>]*href="(/[^"]*)"', re.IGNORECASE)


def count_internal_links(html):
    """Same-site links only (href starting with `/`) — external links
    aren't "internal linking" for this check regardless of domain."""
    if not html:
        return 0
    return len(_INTERNAL_LINK_RE.findall(html))


def analyze_headings(html):
    """Post title is the page's H1, so CMS content should read naturally
    starting from H2 — this only ever checks for H2/H3 (the sanitizer
    doesn't allow H1 in content at all, so "multiple H1" can't happen
    here by construction) and flags an H3 appearing before any H2.
    """
    _, toc = inject_heading_ids_and_get_toc(html)
    warnings = []
    if not toc:
        warnings.append("No headings (H2) found — long articles are easier to scan with section headings.")
    else:
        seen_h2 = False
        for entry in toc:
            if entry["level"] == 2:
                seen_h2 = True
            elif entry["level"] == 3 and not seen_h2:
                warnings.append("An H3 appears before any H2 — heading levels should nest, not skip.")
                break
    return warnings


# ---------------------------------------------------------------------------
# Per-post SEO checker — an internal quality assistant for the admin panel,
# not a ranking predictor. Cheap enough to run on every post-edit page load
# (a handful of regex passes over one post's content), unlike the sitewide
# SEO health dashboard, which the spec explicitly allows to be pricier.
# ---------------------------------------------------------------------------
MIN_CONTENT_WORDS = 300


def analyze_post_seo(post):
    checks = []

    checks.append({"label": "SEO Title", "ok": bool(post.meta_title), "detail": "Set" if post.meta_title else "Falls back to the post title — consider setting one."})
    checks.append({
        "label": "Meta Description", "ok": bool(post.meta_description or post.excerpt),
        "detail": "Set" if post.meta_description else ("Falls back to the excerpt." if post.excerpt else "Missing — add a meta description or an excerpt."),
    })
    checks.append({"label": "Clean Slug", "ok": bool(post.slug) and len(post.slug) <= 75, "detail": post.slug or "Missing"})
    checks.append({
        "label": "Canonical", "ok": True,
        "detail": post.canonical_url if post.canonical_url else "Defaults to this post's own URL.",
    })

    word_count = post.word_count
    checks.append({
        "label": "Content Length", "ok": word_count >= MIN_CONTENT_WORDS,
        "detail": f"{word_count} words" + ("" if word_count >= MIN_CONTENT_WORDS else f" — under the {MIN_CONTENT_WORDS} suggested minimum"),
    })

    heading_warnings = analyze_headings(post.content) if word_count >= MIN_CONTENT_WORDS else []
    checks.append({
        "label": "Heading Structure", "ok": not heading_warnings,
        "detail": "; ".join(heading_warnings) if heading_warnings else "Looks good.",
    })

    internal_links = count_internal_links(post.content)
    checks.append({
        "label": "Internal Links", "ok": internal_links > 0 or word_count < MIN_CONTENT_WORDS,
        "detail": f"{internal_links} internal link{'s' if internal_links != 1 else ''}" if internal_links else "This article has 0 internal links.",
    })

    return checks


def get_related_posts(post, limit=4):
    """Related-post foundation: same category or shared tags, published
    only. Content-similarity/embedding-based recommendations are a later,
    separate step — this starts with plain relational queries.
    """
    from django.db.models import Q

    tag_ids = list(post.tags.values_list("pk", flat=True))
    candidates = Q(category_id=post.category_id) & Q(category_id__isnull=False)
    if tag_ids:
        candidates |= Q(tags__in=tag_ids)

    return (
        published_posts_queryset()
        .filter(candidates)
        .exclude(pk=post.pk)
        .prefetch_related("tags")
        .distinct()
        .order_by("-published_at")[:limit]
    )
