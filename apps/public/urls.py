from django.urls import path

from .views import blog, feeds, home, pages, preview, search
from .views import sitemaps as sitemap_views

app_name = "public"

urlpatterns = [
    path("", home.home, name="home"),
    path("preview/post/<str:token>/", preview.token_preview, name="token-preview"),
    path("blog/", blog.blog_list, name="blog-list"),
    # str (not slug) converter: post/category/tag slugs may contain
    # Unicode combining marks (see apps/blog/fields.py) that the built-in
    # `slug` converter's ASCII-only regex would reject.
    path("blog/<str:slug>/", blog.post_detail, name="post-detail"),
    path("category/<str:slug>/", blog.category_detail, name="category-detail"),
    path("tag/<str:slug>/", blog.tag_detail, name="tag-detail"),
    path("author/<str:username>/", blog.author_detail, name="author-detail"),
    path("search/", search.search, name="search"),
    path("about/", pages.about, name="about"),
    path("contact/", pages.contact, name="contact"),
    path("privacy-policy/", pages.privacy, name="privacy"),
    path("terms/", pages.terms, name="terms"),
    path("feed/", feeds.rss_feed, name="feed"),
    path("sitemap.xml", sitemap_views.sitemap_index, name="sitemap-index"),
    path("sitemap-<str:section>.xml", sitemap_views.sitemap_section, name="sitemap-section"),
]
