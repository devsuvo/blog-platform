"""Sitemap sections, built on Django's own sitemap framework rather than
hand-written XML — `django.contrib.sitemaps` already handles pagination
(the `limit` attribute), escaping, and the index/section split (item 19's
"sitemap index" requirement) correctly; reimplementing that would just be
a worse version of something Django ships.

Never include: drafts, scheduled posts, archived posts, admin/search/
preview URLs — every `items()` here funnels through the same
`published_posts_queryset()` the rest of the public site uses, so
"published" has exactly one definition site-wide.
"""
from django.contrib.auth import get_user_model
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.blog.models import Category, Tag
from apps.blog.services import published_posts_queryset

User = get_user_model()


class PostSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return published_posts_queryset().order_by("-published_at")

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.5

    def items(self):
        published_ids = published_posts_queryset().values_list("pk", flat=True)
        return Category.objects.filter(posts__in=published_ids).distinct()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


class TagSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.4

    def items(self):
        published_ids = published_posts_queryset().values_list("pk", flat=True)
        return Tag.objects.filter(posts__in=published_ids).distinct()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return obj.get_absolute_url()


class AuthorSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.3

    def items(self):
        published_ids = published_posts_queryset().values_list("pk", flat=True)
        return User.objects.filter(posts__in=published_ids).distinct().order_by("pk")

    def location(self, obj):
        return reverse("public:author-detail", kwargs={"username": obj.username})


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return ["public:home", "public:blog-list", "public:about", "public:contact", "public:privacy", "public:terms"]

    def location(self, item):
        return reverse(item)


SITEMAPS = {
    "posts": PostSitemap(),
    "categories": CategorySitemap(),
    "tags": TagSitemap(),
    "authors": AuthorSitemap(),
    "static": StaticViewSitemap(),
}
