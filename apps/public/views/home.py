from django.shortcuts import render

from apps.blog.services import (
    get_category_summary,
    get_featured_posts,
    get_latest_posts,
    get_popular_posts,
)
from apps.public.seo import build_page_seo, get_site_description, get_site_name, safe_json_ld, website_json_ld

# Curated one-line blurbs for the "Explore Topics" section, keyed by category
# name. A category without a DB `description` and not listed here still
# renders — see the generic fallback in `_topics_with_blurbs()` — so a newly
# created category never breaks the homepage.
_TOPIC_BLURBS = {
    "python": "Programming fundamentals, clean code, automation and practical development.",
    "django": "Build secure, scalable and maintainable web applications with Django.",
    "web development": "Frontend, backend, APIs, architecture and deployment.",
    "backend": "Architecture, APIs, databases, caching and scalable application design.",
    "databases": "PostgreSQL, database design, queries and optimization.",
    "devops": "Deployment, servers, caching, CI/CD and production practices.",
    "security": "Practical security principles for web applications and backend systems.",
}


def _topics_with_blurbs(categories):
    topics = []
    for category in categories:
        blurb = category.get("description") or _TOPIC_BLURBS.get(category["name"].lower()) or f"Articles about {category['name']}."
        topics.append({**category, "blurb": blurb})
    return topics


def home(request):
    seo = build_page_seo(
        request, title=f"{get_site_name()} — {get_site_description()}",
        description=get_site_description(), path="/",
    )
    categories = get_category_summary()
    context = {
        "latest_posts": get_latest_posts(limit=6),
        "featured_posts": get_featured_posts(limit=4),
        "popular_posts": get_popular_posts(limit=5),
        "categories": categories,
        "topics": _topics_with_blurbs(categories),
        "website_ld": safe_json_ld(website_json_ld(request)),
        **seo,
    }
    return render(request, "public/home.html", context)
