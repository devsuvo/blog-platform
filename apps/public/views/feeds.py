from django.conf import settings
from django.contrib.syndication.views import Feed
from django.http import HttpResponse
from django.urls import reverse
from django.utils.feedgenerator import Rss201rev2Feed

from apps.blog.services import published_posts_queryset, rss_feed_cache_key
from apps.core.cache import get_or_set_with_lock
from apps.public.seo import get_meta_description, get_site_description, get_site_name


class LatestPostsFeed(Feed):
    """Foundation RSS feed — published posts only, newest first, same
    publication rules as the public site (drafts/scheduled/archived can
    never appear). A full feed reader experience (per-category feeds,
    media enclosures, etc.) is a later step; this is deliberately the
    minimal, correct version.

    `title`/`description` are methods, not class attributes, so a change
    to Site Settings takes effect on the next request rather than needing
    a process restart.
    """

    feed_type = Rss201rev2Feed

    def title(self):
        return get_site_name()

    def description(self):
        return get_site_description()

    def link(self):
        return reverse("public:home")

    def items(self):
        return published_posts_queryset().order_by("-published_at")[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return get_meta_description(item.meta_description, item.excerpt)

    def item_link(self, item):
        return item.get_absolute_url()

    def item_author_name(self, item):
        return item.author.get_full_name() or item.author.username

    def item_pubdate(self, item):
        return item.published_at

    def item_updateddate(self, item):
        return item.updated_at


_feed = LatestPostsFeed()


def rss_feed(request):
    """Thin caching wrapper around `LatestPostsFeed` — same pattern as the
    sitemap views (cache the rendered bytes under a named key, invalidated
    from `invalidate_post_caches` on the next publish/edit/archive, safety
    net TTL from settings.CACHE_TTL_RSS in between). The feed itself stays
    a plain `Feed` subclass so `./manage.py` tooling and Django's own
    syndication tests still see an ordinary, introspectable feed class.
    """
    content = get_or_set_with_lock(
        rss_feed_cache_key(),
        lambda: _feed(request).content,
        getattr(settings, "CACHE_TTL_RSS", 600),
    )
    return HttpResponse(content, content_type="application/rss+xml; charset=utf-8")
