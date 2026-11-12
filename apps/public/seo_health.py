"""Real, database-computed SEO health metrics for the admin SEO dashboard
and the `seo_report`/`check_seo` management commands. Nothing here is
estimated or faked — every number is a direct query result.

Deliberately admin-only / on-demand: this is exactly the "more expensive
analysis" the spec says is fine off the public request path, as long as it
never runs on a page a visitor loads.
"""
import re
from collections import defaultdict

from django.urls import Resolver404, resolve

from apps.blog.models import Category, Post, Tag
from apps.blog.services import published_posts_queryset

from .models import Redirect

_SLUG_SUFFIX_RE = re.compile(r"^(.*)-(\d+)$")


def redirect_target_resolves(entry):
    """External targets can't be verified without a network fetch, so
    they're assumed fine — "broken" here means "points at a path that
    doesn't resolve on this site," a check we can actually make cheaply.
    """
    if not entry.new_path:
        return False
    if entry.new_path.startswith(("http://", "https://")):
        return True
    try:
        resolve(entry.new_path.split("?", 1)[0])
        return True
    except Resolver404:
        return False


def find_duplicate_slug_groups(slugs):
    """Slugs following the auto-uniquify pattern `base-N` grouped by their
    shared `base` — a real, cheap signal that two posts started from the
    same title, surfaced so an editor can check they're not accidental
    near-duplicates.
    """
    groups = defaultdict(list)
    for slug in slugs:
        match = _SLUG_SUFFIX_RE.match(slug)
        base = match.group(1) if match else slug
        groups[base].append(slug)
    return {base: found for base, found in groups.items() if len(found) > 1}


def compute_seo_health():
    published = published_posts_queryset()
    published_ids = list(published.values_list("pk", flat=True))

    redirects = list(Redirect.objects.all())
    broken_redirects = [entry for entry in redirects if not redirect_target_resolves(entry)]

    return {
        "total_posts": Post.objects.count(),
        "published_posts": len(published_ids),
        "indexed_posts": published.filter(robots_index=True).count(),
        "missing_seo_title": published.filter(meta_title="").count(),
        "missing_meta_description": published.filter(meta_description="", excerpt="").count(),
        "missing_category": published.filter(category__isnull=True).count(),
        "empty_categories": Category.objects.exclude(posts__in=published_ids).distinct().count(),
        "empty_tags": Tag.objects.exclude(posts__in=published_ids).distinct().count(),
        "duplicate_slug_groups": find_duplicate_slug_groups(published.values_list("slug", flat=True)),
        "redirects_total": len(redirects),
        "redirects_broken": len(broken_redirects),
        "broken_redirects": broken_redirects,
    }
