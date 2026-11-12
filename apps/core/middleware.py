from .request_context import get_request_id, new_request_id, reset_request_id, set_request_id


class RequestIDMiddleware:
    """Assigns every request a short ID, exposed on the response as
    `X-Request-ID` and available to every log line emitted while handling
    it (via a contextvar + `apps.core.logging_utils.RequestIDLogFilter`).

    Placed first in MIDDLEWARE (right after SecurityMiddleware) so the ID
    covers the entire request — including anything logged by
    authentication, permission checks, or an unhandled exception.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = new_request_id(request.META.get("HTTP_X_REQUEST_ID", ""))
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)
        response["X-Request-ID"] = request_id
        return response


# Re-exported for call sites that only need to read the current value
# (e.g. error views adding it to a support-contact message) without
# importing the lower-level context module directly.
__all__ = ["RequestIDMiddleware", "get_request_id"]
