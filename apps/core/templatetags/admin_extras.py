from django import template

register = template.Library()


@register.filter
def can_publish_post(user, post):
    from apps.blog.permissions import can_publish_post as _can_publish_post

    return _can_publish_post(user, post)


@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """Build a query string from the current request's GET params with the
    given keys replaced/removed, e.g. `?{% query_string page=3 %}` keeps
    `q=`/`role=`/etc. intact while only swapping the page number.
    """
    request = context["request"]
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
