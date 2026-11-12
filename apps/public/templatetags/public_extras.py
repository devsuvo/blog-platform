from django import template

from apps.public.seo import canonical_url as _canonical_url

register = template.Library()


@register.simple_tag(takes_context=True)
def canonical_url(context, path=None, query=None):
    return _canonical_url(context["request"], path=path, query=query)


@register.simple_tag
def elided_page_range(paginator, number):
    """Django templates can't call a method with keyword arguments, so
    `Paginator.get_elided_page_range(on_each_side=1, on_ends=1)` (which
    produces the "1 2 3 … 10" shape) needs this small wrapper.
    """
    return list(paginator.get_elided_page_range(number, on_each_side=1, on_ends=1))


@register.filter
def readable_date(value):
    """13 August 2026 — used everywhere instead of Django's default date
    formatting so publish/updated dates read consistently site-wide."""
    if not value:
        return ""
    return value.strftime("%d %B %Y")
