from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models

_MAX_REDIRECT_CHAIN_DEPTH = 10
_DANGEROUS_SCHEME_MARKERS = ("javascript:", "data:", "vbscript:")


class RedirectStatusCode(models.IntegerChoices):
    PERMANENT = 301, "301 Permanent"
    TEMPORARY = 302, "302 Temporary"


def _normalize_redirect_path(value):
    value = (value or "").strip()
    lowered = value.lower()
    if any(marker in lowered for marker in _DANGEROUS_SCHEME_MARKERS):
        raise ValidationError(f"'{value}' uses an unsafe URL scheme.")
    if lowered.startswith("http://") or lowered.startswith("https://"):
        URLValidator(schemes=["http", "https"])(value)
        return value
    if not value.startswith("/"):
        value = "/" + value
    return value


class Redirect(models.Model):
    """Admin-managed URL redirects, plus the ones created automatically
    when a published post's slug changes (`is_auto=True`) — one unified
    table so there's a single place that answers "where does this old URL
    go now?" instead of two overlapping systems.
    """

    old_path = models.CharField(
        max_length=500, unique=True, db_index=True,
        help_text="A path on this site, e.g. /blog/old-slug/",
    )
    new_path = models.CharField(
        max_length=500,
        help_text="A path on this site, or a full https:// URL to redirect elsewhere.",
    )
    status_code = models.PositiveSmallIntegerField(
        choices=RedirectStatusCode.choices, default=RedirectStatusCode.PERMANENT,
    )
    is_auto = models.BooleanField(
        default=False, help_text="Created automatically by a post slug change, not by an admin.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["old_path"])]

    def __str__(self):
        return f"{self.old_path} → {self.new_path} ({self.status_code})"

    def clean(self):
        old_path = _normalize_redirect_path(self.old_path)
        if old_path.startswith(("http://", "https://")):
            raise ValidationError({"old_path": "The old URL must be a path on this site, e.g. /blog/old-slug/."})
        new_path = _normalize_redirect_path(self.new_path)

        if old_path == new_path:
            raise ValidationError({"new_path": "A redirect cannot point to itself."})

        # Walk the chain starting at new_path; if it ever leads back to
        # old_path (directly, or via A→B→C→A), this redirect would loop.
        current = new_path
        for _ in range(_MAX_REDIRECT_CHAIN_DEPTH):
            next_hop = (
                Redirect.objects.filter(old_path=current)
                .exclude(pk=self.pk)
                .values_list("new_path", flat=True)
                .first()
            )
            if next_hop is None:
                break
            if next_hop == old_path:
                raise ValidationError({"new_path": "This redirect would create a loop with an existing redirect."})
            current = next_hop

        self.old_path = old_path
        self.new_path = new_path

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ContactMessage(models.Model):
    """Stores contact-form submissions. An email notification is also sent
    at submit time (see forms.py); this row is the durable record in case
    the outgoing email fails or someone needs to search past messages.
    """

    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField(max_length=5000)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        default_permissions = ("view", "delete")

    def __str__(self):
        return f"{self.subject} — {self.email}"


class SearchQueryStat(models.Model):
    """Aggregated (not raw-per-search) record of what visitors search for —
    one row per normalized query with a running count, the same
    aggregate-not-per-event shape as `NotFoundLog`. Never grows one row per
    search; retention is a prune (see `apps.public.services.prune_search_query_stats`),
    not an unbounded table.
    """

    query = models.CharField(max_length=200, unique=True, db_index=True)
    hit_count = models.PositiveIntegerField(default=1)
    last_searched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-hit_count"]
        default_permissions = ("view", "delete")
        indexes = [models.Index(fields=["-hit_count"])]

    def __str__(self):
        return f"{self.query} ({self.hit_count})"
