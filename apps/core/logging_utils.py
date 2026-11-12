import json
import logging

from .request_context import get_request_id

# Attributes every stdlib LogRecord already carries — anything else passed
# via `logger.info(..., extra={...})` is application-supplied context and
# gets folded into the JSON output.
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class RequestIDLogFilter(logging.Filter):
    """Stamps `record.request_id` from the current request's contextvar
    (or "-" outside a request, e.g. a management command or Celery task
    run standalone) so every formatter can reference `%(request_id)s`
    unconditionally — Python's logging raises if a format field is
    missing from a record, so this has to run on every handler, not just
    request-triggered ones.
    """

    def filter(self, record):
        record.request_id = get_request_id()
        return True


class JSONFormatter(logging.Formatter):
    """One JSON object per line — the shape a log aggregator (CloudWatch,
    Loki, ELK, ...) expects, so production doesn't need a vendor-specific
    log shipper config beyond "this is JSON". Development keeps the
    plain-text 'verbose' formatter instead; it's easier to read in a
    terminal and there's no aggregator to feed there.
    """

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "module": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key not in payload:
                try:
                    json.dumps(value)  # only include values that are actually serializable
                except TypeError:
                    value = repr(value)
                payload[key] = value

        return json.dumps(payload, default=str)
