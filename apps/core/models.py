from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class ActivityAction(models.TextChoices):
    LOGIN = "login", _("Logged in")
    LOGOUT = "logout", _("Logged out")
    LOGIN_FAILED = "login_failed", _("Failed login attempt")
    USER_CREATED = "user_created", _("Created user")
    USER_UPDATED = "user_updated", _("Updated user")
    ROLE_CHANGED = "role_changed", _("Changed role")
    PERMISSION_CHANGED = "permission_changed", _("Changed permissions")
    STATUS_CHANGED = "status_changed", _("Changed status")
    USER_DELETED = "user_deleted", _("Deleted user")
    PASSWORD_CHANGED = "password_changed", _("Changed password")
    PASSWORD_RESET_REQUESTED = "password_reset_requested", _("Requested password reset")
    PROFILE_UPDATED = "profile_updated", _("Updated profile")
    SETTINGS_CHANGED = "settings_changed", _("Changed settings")

    POST_CREATED = "post_created", _("Created post")
    POST_UPDATED = "post_updated", _("Updated post")
    POST_PUBLISHED = "post_published", _("Published post")
    POST_SCHEDULED = "post_scheduled", _("Scheduled post")
    POST_ARCHIVED = "post_archived", _("Archived post")
    POST_RESTORED = "post_restored", _("Restored post")
    POST_DELETED = "post_deleted", _("Deleted post")
    REVISION_CREATED = "revision_created", _("Created revision")
    REVISION_RESTORED = "revision_restored", _("Restored revision")
    CATEGORY_CREATED = "category_created", _("Created category")
    CATEGORY_UPDATED = "category_updated", _("Updated category")
    CATEGORY_DELETED = "category_deleted", _("Deleted category")
    TAG_CREATED = "tag_created", _("Created tag")
    TAG_UPDATED = "tag_updated", _("Updated tag")
    TAG_DELETED = "tag_deleted", _("Deleted tag")
    REDIRECT_CREATED = "redirect_created", _("Created redirect")
    REDIRECT_UPDATED = "redirect_updated", _("Updated redirect")
    REDIRECT_DELETED = "redirect_deleted", _("Deleted redirect")

    POST_TRASHED = "post_trashed", _("Moved post to trash")
    POST_RESTORED_FROM_TRASH = "post_restored_from_trash", _("Restored post from trash")
    POST_PERMANENTLY_DELETED = "post_permanently_deleted", _("Permanently deleted post")
    POST_DUPLICATED = "post_duplicated", _("Duplicated post")
    PREVIEW_LINK_CREATED = "preview_link_created", _("Created preview link")
    TAG_MERGED = "tag_merged", _("Merged tags")
    POSTS_EXPORTED = "posts_exported", _("Exported posts")
    USERS_EXPORTED = "users_exported", _("Exported users")


class ActivityLog(models.Model):
    """Immutable audit trail. Entries are written by the application, never
    edited or removed through the admin panel — only `view` is a valid
    permission, so nothing here can be tampered with after the fact.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
        help_text=_("The user who performed the action. Null for system/anonymous events."),
    )
    action = models.CharField(max_length=32, choices=ActivityAction.choices)
    description = models.CharField(max_length=255, blank=True)

    target_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    target_object_id = models.CharField(max_length=64, null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        default_permissions = ("view",)
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["actor"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        who = self.actor if self.actor_id else _("System")
        return f"{who} — {self.get_action_display()}"


class RobotsDefault(models.TextChoices):
    INDEX_FOLLOW = "index, follow", _("index, follow")
    NOINDEX_FOLLOW = "noindex, follow", _("noindex, follow")
    NOINDEX_NOFOLLOW = "noindex, nofollow", _("noindex, nofollow")


class SiteSetting(models.Model):
    """Site-wide SEO/identity settings, editable from the Admin Panel with
    no code changes. A deliberate singleton (see `load()`/`save()`) —
    there is exactly one site, so one settings row, cached between saves.
    """

    site_title = models.CharField(
        max_length=70, blank=True,
        help_text=_("Shown in the browser tab and search results, e.g. 'Python Developer Blog'."),
    )
    site_name = models.CharField(
        max_length=100, blank=True,
        help_text=_("Used for og:site_name and the JSON-LD publisher name."),
    )
    site_description = models.CharField(max_length=300, blank=True)

    default_meta_description = models.CharField(
        max_length=300, blank=True,
        help_text=_("Used when a page/post doesn't set its own meta description."),
    )
    default_robots = models.CharField(
        max_length=30, choices=RobotsDefault.choices, default=RobotsDefault.INDEX_FOLLOW,
    )
    default_og_title = models.CharField(max_length=95, blank=True)
    default_og_description = models.CharField(max_length=200, blank=True)
    twitter_username = models.CharField(
        max_length=50, blank=True, help_text=_("Without the @ — used as twitter:site.")
    )
    canonical_domain = models.CharField(
        max_length=255, blank=True,
        help_text=_("e.g. https://example.com — overrides SITE_URL when set. Leave blank to use the request's own host."),
    )

    facebook_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)

    # --- General ---
    posts_per_page = models.PositiveSmallIntegerField(
        default=12, help_text=_("Posts shown per page on the blog index, category, tag, and author pages."),
    )

    # --- Publishing ---
    allow_authors_to_publish = models.BooleanField(
        default=True,
        help_text=_(
            "Global switch for the Author role specifically: off means an Author can never "
            "publish directly (even if individually granted the permission) — only submit "
            "drafts for an Editor/Admin to publish. Does not affect Editor/Admin/Super Admin. "
            "Defaults on so granting an Author the Publish permission keeps working as before "
            "this setting existed; turn it off only to add an extra approval gate."
        ),
    )
    enable_scheduled_publishing = models.BooleanField(
        default=True, help_text=_("Off hides the Schedule option — everyone publishes immediately or saves a draft."),
    )
    default_reading_speed_wpm = models.PositiveSmallIntegerField(
        default=225, help_text=_("Words per minute used to estimate each post's reading time."),
    )

    # --- Analytics ---
    analytics_enabled = models.BooleanField(
        default=True, help_text=_("Off disables all view-count aggregation — no new data is recorded."),
    )
    analytics_retention_days = models.PositiveIntegerField(
        default=395, help_text=_("Daily view-count rows older than this are pruned by the cleanup task."),
    )
    track_search = models.BooleanField(
        default=True, help_text=_("Aggregate what visitors search for, to surface top search terms in the dashboard."),
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("change", "view")
        verbose_name = _("site settings")
        verbose_name_plural = _("site settings")

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        from .services import site_settings_cache_key

        from django.core.cache import cache

        cache.delete(site_settings_cache_key())

    def delete(self, *args, **kwargs):
        raise TypeError("SiteSetting is a singleton and cannot be deleted.")

    @classmethod
    def load(cls):
        from django.core.cache import cache

        from .services import site_settings_cache_key, site_settings_cache_ttl

        cache_key = site_settings_cache_key()
        obj = cache.get(cache_key)
        if obj is None:
            obj, _created = cls.objects.get_or_create(pk=1)
            cache.set(cache_key, obj, site_settings_cache_ttl())
        return obj

    @property
    def social_links(self):
        """Only the social profiles that are actually configured — never
        fabricate a URL for a platform the site owner hasn't set up.
        """
        fields = [
            ("Facebook", self.facebook_url),
            ("X", self.x_url),
            ("LinkedIn", self.linkedin_url),
            ("GitHub", self.github_url),
            ("YouTube", self.youtube_url),
        ]
        return [(label, url) for label, url in fields if url]


class NotFoundLog(models.Model):
    """Sampled record of requested paths that 404'd, so broken/missing
    links can be found and turned into redirects. Deliberately lightweight:
    one row per distinct path with a running count, not one row per hit.
    """

    path = models.CharField(max_length=500, unique=True, db_index=True)
    referrer = models.CharField(max_length=500, blank=True)
    hit_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen"]
        default_permissions = ("view", "delete")
        indexes = [models.Index(fields=["-hit_count"]), models.Index(fields=["-last_seen"])]

    def __str__(self):
        return f"{self.path} ({self.hit_count})"
