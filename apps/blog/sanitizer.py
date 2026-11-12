"""HTML sanitization for user-authored post content.

Content comes from the rich text editor as HTML and is untrusted input —
sanitize on write (here) so it can be trusted on read (`{{ post.content|safe }}`)
without re-sanitizing on every render. Never mark editor output safe without
running it through this first.
"""
import nh3

ALLOWED_TAGS = {
    "p", "br", "hr",
    "h2", "h3", "h4",
    "strong", "b", "em", "i", "u", "s",
    "a",
    "ul", "ol", "li",
    "blockquote",
    "pre", "code",
    "img",
    "table", "thead", "tbody", "tr", "th", "td",
}

ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height", "loading"},
}

ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_post_html(raw_html):
    """Strip scripts, event handlers, unsafe iframes/embeds, and anything
    outside the editor's supported formatting set. Returns clean HTML safe
    to store and later render with `|safe`.
    """
    if not raw_html:
        return ""
    return nh3.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
