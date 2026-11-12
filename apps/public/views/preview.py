from django.http import Http404
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from apps.blog.models import PostPreviewToken
from apps.blog.services import get_related_posts, inject_heading_ids_and_get_toc


@ratelimit(key="ip", rate="20/m", method="GET", block=True)
def token_preview(request, token):
    """A shareable, time-limited view of a not-yet-public post — the
    token (not login, not the post's ID/slug) is the only thing that
    grants access. Always noindex/nofollow regardless of the post's own
    SEO settings, never linked from the sitemap or RSS, and never counted
    as a real page view or search-indexable content.

    A missing OR expired token both 404 — never a distinct "expired"
    message, which would confirm to a guesser that the token format was
    at least *structurally* valid.
    """
    try:
        preview_token = PostPreviewToken.objects.select_related(
            "post", "post__author", "post__category",
        ).prefetch_related("post__tags").get(token=token)
    except PostPreviewToken.DoesNotExist:
        raise Http404

    if not preview_token.is_valid():
        raise Http404

    post = preview_token.post
    content_with_ids, toc = inject_heading_ids_and_get_toc(post.content)

    context = {
        "post": post,
        "article_content": content_with_ids,
        "toc": toc if len(toc) >= 3 else [],
        "related_posts": get_related_posts(post, limit=3),
        "preview_expires_at": preview_token.expires_at,
        "seo_title": f"Preview: {post.title}",
        "seo_description": None,
        "canonical": None,
        "robots": "noindex, nofollow",
        "og": {},
        "twitter": {},
    }
    return render(request, "public/preview_token.html", context)
