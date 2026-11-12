from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import F
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.blog.analytics import record_post_view
from apps.blog.models import Category, Post, Tag
from apps.blog.services import (
    get_author_post_ids,
    get_category_post_ids,
    get_category_summary,
    get_latest_posts,
    get_popular_posts,
    get_published_post_count,
    get_related_posts,
    get_tag_post_ids,
    inject_heading_ids_and_get_toc,
    paginate_post_ids,
    post_detail_cache_key,
    published_posts_queryset,
)
from apps.public.seo import (
    article_json_ld,
    breadcrumb_json_ld,
    build_page_seo,
    build_post_seo,
    canonical_url,
    robots_for_listing,
    safe_json_ld,
    webpage_json_ld,
)

User = get_user_model()
PAGE_SIZE = 12


def blog_list(request):
    categories = get_category_summary()
    active_category = request.GET.get("category") or None
    # Silently ignore an unknown/stale category slug rather than 404 — it
    # just falls back to "All", the same graceful behavior as an empty filter.
    if active_category and not any(c["slug"] == active_category for c in categories):
        active_category = None

    posts = published_posts_queryset().prefetch_related("tags").order_by("-published_at")
    if active_category:
        posts = posts.filter(category__slug=active_category)
    paginator = Paginator(posts, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    query_parts = []
    if active_category:
        query_parts.append(f"category={active_category}")
    if page_obj.number > 1:
        query_parts.append(f"page={page_obj.number}")

    seo = build_page_seo(
        request, title="Blog", description="All articles.",
        query="&".join(query_parts) or None,
    )
    context = {
        "page_obj": page_obj,
        "categories": categories,
        "active_category": active_category,
        "total_count": get_published_post_count(),
        "recent_posts": get_latest_posts(limit=5),
        "popular_posts": get_popular_posts(limit=5),
        "blog_ld": safe_json_ld(webpage_json_ld(request, seo, schema_type="Blog")),
        **seo,
    }
    return render(request, "public/blog_list.html", context)


def post_detail(request, slug):
    # A 404 here (e.g. the slug was renamed) is handled generically by
    # RedirectMiddleware, which checks the Redirect table for any old path
    # on the site — not just posts — before giving up with a real 404.
    post = get_object_or_404(published_posts_queryset().prefetch_related("tags"), slug=slug)

    _record_view(request, post)

    cache_key = post_detail_cache_key(post.slug)
    cached = cache.get(cache_key)
    if cached is None:
        content_with_ids, toc = inject_heading_ids_and_get_toc(post.content)
        cached = {"content": content_with_ids, "toc": toc}
        cache.set(cache_key, cached, getattr(settings, "CACHE_TTL_POST_CONTENT", 3600))

    breadcrumbs = []
    if post.category:
        breadcrumbs.append((post.category.name, post.category.get_absolute_url()))
    breadcrumbs.append((post.title, None))

    seo = build_post_seo(request, post)

    context = {
        "post": post,
        "article_content": cached["content"],
        "toc": cached["toc"] if len(cached["toc"]) >= 3 else [],
        "related_posts": get_related_posts(post, limit=6),
        "breadcrumbs": breadcrumbs,
        "breadcrumb_ld": safe_json_ld(breadcrumb_json_ld(request, [("Home", "/")] + breadcrumbs)),
        "article_ld": safe_json_ld(article_json_ld(request, post, seo=seo)),
        "article_share_url": canonical_url(request),
        **seo,
    }
    return render(request, "public/post_detail.html", context)


def _record_view(request, post):
    viewed = request.session.get("viewed_post_ids", [])
    if post.pk in viewed:
        return
    Post.objects.filter(pk=post.pk).update(views_count=F("views_count") + 1)
    post.views_count += 1
    request.session["viewed_post_ids"] = (viewed + [post.pk])[-50:]
    record_post_view(post)


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    post_ids = get_category_post_ids(category)
    page_obj = paginate_post_ids(post_ids, request.GET.get("page"), PAGE_SIZE)

    breadcrumbs = [(category.name, None)]
    seo = build_page_seo(
        request, title=category.meta_title or category.name,
        description=category.meta_description or category.description,
        query=f"page={page_obj.number}" if page_obj.number > 1 else None,
        robots=robots_for_listing(page_obj.paginator.count),
    )
    context = {
        "category": category,
        "page_obj": page_obj,
        "breadcrumbs": breadcrumbs,
        "breadcrumb_ld": safe_json_ld(breadcrumb_json_ld(request, [("Home", "/")] + breadcrumbs)),
        **seo,
    }
    return render(request, "public/category_detail.html", context)


def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    post_ids = get_tag_post_ids(tag)
    page_obj = paginate_post_ids(post_ids, request.GET.get("page"), PAGE_SIZE)

    breadcrumbs = [(tag.name, None)]
    seo = build_page_seo(
        request, title=f"#{tag.name}", description=f"Articles tagged {tag.name}.",
        query=f"page={page_obj.number}" if page_obj.number > 1 else None,
        robots=robots_for_listing(page_obj.paginator.count),
    )
    context = {
        "tag": tag,
        "page_obj": page_obj,
        "breadcrumbs": breadcrumbs,
        "breadcrumb_ld": safe_json_ld(breadcrumb_json_ld(request, [("Home", "/")] + breadcrumbs)),
        **seo,
    }
    return render(request, "public/tag_detail.html", context)


def author_detail(request, username):
    author = get_object_or_404(User, username=username)
    post_ids = get_author_post_ids(author)
    page_obj = paginate_post_ids(post_ids, request.GET.get("page"), PAGE_SIZE)

    if page_obj.paginator.count == 0:
        # Never confirm that an arbitrary username exists on the site if
        # they've never actually published anything public.
        raise Http404

    display_name = author.get_full_name() or author.username
    breadcrumbs = [(display_name, None)]
    seo = build_page_seo(
        request, title=display_name, description=f"Articles by {display_name}.",
        query=f"page={page_obj.number}" if page_obj.number > 1 else None,
        robots=robots_for_listing(page_obj.paginator.count),
    )
    context = {
        "author": author,
        "page_obj": page_obj,
        "breadcrumbs": breadcrumbs,
        "breadcrumb_ld": safe_json_ld(breadcrumb_json_ld(request, [("Home", "/")] + breadcrumbs)),
        **seo,
    }
    return render(request, "public/author_detail.html", context)
