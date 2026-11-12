import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger("apps.public")


def site(request):
    """Site identity available on every template, admin panel included
    (footer/branding may want it later) — cheap, no DB query.
    """
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_DESCRIPTION": settings.SITE_DESCRIPTION,
        "CONTACT_EMAIL": settings.CONTACT_EMAIL,
        "current_year": timezone.now().year,
    }


def seo_defaults(request):
    """Baseline (empty, not missing) values for the SEO context keys
    `public/base.html` reads. Pages built through `apps.public.seo`'s
    `build_page_seo`/`build_post_seo` override these with real values —
    but Django's `{{ x|default:y }}` raises `VariableDoesNotExist` (loudly,
    uncaught) when `y` is a filter *argument* that's entirely absent from
    context, not just falsy. That includes our own error-handler views
    (400/403/404/429/500), which only pass `robots`/`canonical_path`: this
    is what actually keeps a bug on some other page from turning "render a
    friendly 500 page" into an unhandled exception of its own.
    """
    return {"seo_title": None, "seo_description": None, "canonical": None, "og": {}, "twitter": {}}


def nav_categories(request):
    """Categories for the header's Categories menu. Wrapped defensively:
    if the database is unreachable — the classic cause of a real 500 — this
    must not itself raise and turn our custom error page into Django's raw
    fallback response.
    """
    try:
        from apps.blog.services import get_category_summary

        return {"nav_categories": get_category_summary()}
    except Exception:
        logger.exception("nav_categories context processor failed; degrading to empty list")
        return {"nav_categories": []}
