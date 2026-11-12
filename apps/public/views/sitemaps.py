from django.conf import settings
from django.contrib.sitemaps import views as sitemap_views
from django.http import Http404, HttpResponse

from apps.blog.services import sitemap_cache_key
from apps.core.cache import get_or_set_with_lock

from ..sitemaps import SITEMAPS


def _rendered_content(template_response):
    """Django's sitemap/index views return a lazy TemplateResponse —
    `.content` is empty until `.render()` runs.
    """
    template_response.render()
    return template_response.content


def _sitemap_ttl():
    return getattr(settings, "CACHE_TTL_SITEMAP", 1800)


def sitemap_index(request):
    """/sitemap.xml — an index pointing at each cached section, using
    Django's own index-rendering so the XML itself is well-tested code;
    only the caching wrapper here is ours.
    """
    content = get_or_set_with_lock(
        sitemap_cache_key("index"),
        lambda: _rendered_content(sitemap_views.index(request, SITEMAPS, sitemap_url_name="public:sitemap-section")),
        _sitemap_ttl(),
    )
    return HttpResponse(content, content_type="application/xml")


def sitemap_section(request, section):
    if section not in SITEMAPS:
        raise Http404

    content = get_or_set_with_lock(
        sitemap_cache_key(section),
        lambda: _rendered_content(sitemap_views.sitemap(request, SITEMAPS, section=section)),
        _sitemap_ttl(),
    )
    return HttpResponse(content, content_type="application/xml")
