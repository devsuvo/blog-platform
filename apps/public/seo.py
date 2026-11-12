"""Centralized SEO service.

    SiteSetting (admin-editable)
        ↓
    SEO Service (this module)
        ↓
    View builds one seo-context dict per page
        ↓
    Template reads it into meta tags / JSON-LD

Every public view calls into these functions instead of re-deriving
title/description/canonical/robots fallback chains itself — that
duplication (the same `post.meta_title or post.title` logic copy-pasted
into a <title> block, an og:title tag, and a twitter:title tag) is exactly
what this module exists to remove.

Titles/descriptions are user-authored CharFields (not sanitized HTML like
post content), so JSON-LD — embedded in a <script> tag — needs its own
escaping: `json.dumps` alone doesn't stop a title containing `</script>`
from breaking out of the tag. See `safe_json_ld`.
"""
import json

from django.conf import settings
from django.urls import reverse
from django.utils.safestring import mark_safe


def get_site_settings():
    from apps.core.models import SiteSetting

    return SiteSetting.load()


def get_site_name():
    return get_site_settings().site_name or settings.SITE_NAME


def get_site_description():
    return get_site_settings().site_description or settings.SITE_DESCRIPTION


def site_base_url(request):
    """The domain every canonical/OG/JSON-LD URL is built from. Prefers the
    admin-configured canonical domain, then SITE_URL, then falls back to
    the current request — so local dev needs no configuration, but a
    misconfigured proxy in production can't leak an inconsistent domain
    into indexed pages once either setting is filled in.
    """
    domain = (get_site_settings().canonical_domain or settings.SITE_URL or "").rstrip("/")
    if domain:
        return domain
    return request.build_absolute_uri("/").rstrip("/")


def canonical_url(request, path=None, query=None):
    """Absolute canonical URL. `path=None` uses the current request path.
    `query`, if given, is included verbatim (e.g. `page=2`) — paginated
    pages canonicalize to themselves, not to page 1, since each page is
    distinct content. A `path` that's already an absolute URL (an
    explicit custom canonical) is used as-is.
    """
    path = path if path is not None else request.path
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    else:
        url = site_base_url(request) + path
    if query:
        url = f"{url}?{query}"
    return url


def get_seo_title(title=None, fallback_title=None, site_name=None):
    """SEO Title → Post/Page Title → Site Name."""
    site_name = site_name if site_name is not None else get_site_name()
    return title or fallback_title or site_name


def get_meta_description(description=None, excerpt=None):
    """Meta Description → Excerpt → configured site default → ''."""
    return description or excerpt or get_site_settings().default_meta_description or ""


def get_robots(index=True, follow=True):
    return f"{'index' if index else 'noindex'}, {'follow' if follow else 'nofollow'}"


def get_open_graph(request, *, title, description, url, og_type="website"):
    """og:image is deliberately never included — this site has no
    featured-image concept, and a missing/broken og:image is worse for
    link previews than a clean text-only card.
    """
    site_settings = get_site_settings()
    return {
        "site_name": get_site_name(),
        "type": og_type,
        "title": title or site_settings.default_og_title or get_seo_title(),
        "description": description or site_settings.default_og_description or get_meta_description(),
        "url": url,
    }


def get_twitter_meta(*, title, description):
    username = get_site_settings().twitter_username.lstrip("@")
    data = {"card": "summary", "title": title, "description": description}
    if username:
        data["site"] = f"@{username}"
    return data


def build_page_seo(request, *, title=None, description=None, path=None, query=None,
                    robots="index, follow", og_type="website"):
    """Generic per-page SEO context for pages with no dedicated model
    (home, blog index, search, about/contact/privacy/terms).
    """
    title = get_seo_title(fallback_title=title)
    description = get_meta_description(description=description)
    canonical = canonical_url(request, path=path, query=query)
    return {
        "seo_title": title,
        "seo_description": description,
        "canonical": canonical,
        "robots": robots,
        "og": get_open_graph(request, title=title, description=description, url=canonical, og_type=og_type),
        "twitter": get_twitter_meta(title=title, description=description),
    }


def build_post_seo(request, post):
    title = get_seo_title(post.meta_title, post.title)
    description = get_meta_description(post.meta_description, post.excerpt)
    canonical = canonical_url(request, path=post.canonical_url or request.path)
    robots = get_robots(post.robots_index, post.robots_follow)
    og_title = post.og_title or title
    og_description = post.og_description or description
    return {
        "seo_title": title,
        "seo_description": description,
        "canonical": canonical,
        "robots": robots,
        "og": get_open_graph(request, title=og_title, description=og_description, url=canonical, og_type="article"),
        "twitter": get_twitter_meta(title=og_title, description=og_description),
    }


# ---------------------------------------------------------------------------
# Thin-content control: an indexable page with nothing on it is exactly the
# kind of low-value page search engines penalize sites for. Category/tag/
# author views call this to force noindex when there's genuinely nothing
# there yet, without a human needing to remember to do it per-object.
# ---------------------------------------------------------------------------
def robots_for_listing(post_count):
    return get_robots(index=post_count > 0, follow=True)


# ---------------------------------------------------------------------------
# JSON-LD structured data
# ---------------------------------------------------------------------------
def safe_json_ld(data):
    """`json.dumps` a dict for embedding in `<script type="application/ld+json">`,
    escaping `</` so an attacker-controlled string field can't prematurely
    close the script tag and inject markup.
    """
    return mark_safe(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def organization_json_ld(request):
    return {"@type": "Organization", "name": get_site_name(), "url": site_base_url(request) + "/"}


def author_json_ld(request, user):
    """Only real, verifiable data from the actual User profile — never a
    fabricated social profile. `url` is the author's own page on this
    site, the one link we can always honestly provide.
    """
    data = {"@type": "Person", "name": user.get_full_name() or user.username}
    try:
        data["url"] = canonical_url(request, path=reverse("public:author-detail", kwargs={"username": user.username}))
    except Exception:
        pass
    return data


def article_json_ld(request, post, seo=None):
    seo = seo or build_post_seo(request, post)
    data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": seo["seo_title"],
        "description": seo["seo_description"],
        "datePublished": post.published_at.isoformat() if post.published_at else None,
        "dateModified": post.updated_at.isoformat() if post.updated_at else None,
        "author": author_json_ld(request, post.author),
        "mainEntityOfPage": {"@type": "WebPage", "@id": seo["canonical"]},
        "publisher": organization_json_ld(request),
    }
    return {key: value for key, value in data.items() if value is not None}


def breadcrumb_json_ld(request, items):
    """`items` is an ordered list of (label, path_or_None) tuples; the last
    entry (the current page) typically has no link.
    """
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": label,
                **({"item": canonical_url(request, path=path)} if path else {}),
            }
            for position, (label, path) in enumerate(items, start=1)
        ],
    }


def webpage_json_ld(request, seo, schema_type="WebPage"):
    """Generic structured data for pages with no dedicated builder (About,
    Blog index) — reuses whatever `build_page_seo()` already computed
    rather than re-deriving title/description/canonical.
    """
    return {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": seo["seo_title"],
        "description": seo["seo_description"],
        "url": seo["canonical"],
    }


def website_json_ld(request):
    """Homepage-only. `potentialAction`/`SearchAction` is included because
    /search/?q= genuinely works this way — never describe behavior the
    site doesn't actually have.
    """
    search_url = site_base_url(request) + reverse("public:search")
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": get_site_name(),
        "url": site_base_url(request) + "/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": f"{search_url}?q={{search_term_string}}"},
            "query-input": "required name=search_term_string",
        },
    }
