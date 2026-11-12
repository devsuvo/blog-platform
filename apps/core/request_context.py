"""A per-request ID, available anywhere in the call stack without having
to thread `request` through every function — including inside Celery task
bodies invoked synchronously from a request, and in log records emitted
by code that has no `request` argument at all (e.g. model `save()`).

Kept as its own module (no Django/logging imports) so both
`apps.core.middleware` and `apps.core.logging_utils` can depend on it
without importing each other.
"""
import contextvars
import re
import uuid

_request_id_var = contextvars.ContextVar("request_id", default="-")
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_-]")


def new_request_id(client_supplied=""):
    """Build a request ID: reuse a client-supplied X-Request-ID (useful
    behind a proxy/load balancer that already assigns one, so a single ID
    traces the whole hop chain) if it looks safe, otherwise mint a fresh
    one. Sanitized before it ever reaches a log line or response header —
    an unsanitized client header is a log-injection vector.
    """
    cleaned = _SAFE_ID_RE.sub("", client_supplied or "")[:64]
    return cleaned or uuid.uuid4().hex[:12]


def set_request_id(request_id):
    return _request_id_var.set(request_id)


def reset_request_id(token):
    _request_id_var.reset(token)


def get_request_id():
    return _request_id_var.get()
