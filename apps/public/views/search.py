from urllib.parse import quote

from django.core.paginator import Paginator
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from apps.blog.services import search_posts
from apps.public.seo import build_page_seo, get_site_name
from apps.public.services import record_search_query

PAGE_SIZE = 10


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
def search(request):
    query = request.GET.get("q", "").strip()[:200]
    page_obj = None

    if query:
        results = search_posts(query)
        paginator = Paginator(results, PAGE_SIZE)
        page_obj = paginator.get_page(request.GET.get("page"))
        record_search_query(query)

    title = f'Search results for "{query}"' if query else "Search"
    seo = build_page_seo(
        request, title=f"{title} — {get_site_name()}", description=f"Search articles on {get_site_name()}.",
        query=f"q={quote(query)}" if query else None,
        robots="noindex, follow",
    )
    context = {"query": query, "page_obj": page_obj, **seo}
    return render(request, "public/search.html", context)
