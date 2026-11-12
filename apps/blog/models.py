import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .fields import ContentSlugField

ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
READING_WPM = 225


def post_image_upload_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"blog/inline/{uuid.uuid4().hex}.{extension}"


def validate_image_size(file):
    if file.size > MAX_IMAGE_SIZE_BYTES:
        raise ValidationError(_("Image file size may not exceed 5 MB."))


class PostStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    SCHEDULED = "scheduled", _("Scheduled")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = ContentSlugField(max_length=120, unique=True, allow_unicode=True)
    description = models.TextField(blank=True)
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        indexes = [models.Index(fields=["slug"]), models.Index(fields=["parent"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("public:category-detail", kwargs={"slug": self.slug})


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = ContentSlugField(max_length=60, unique=True, allow_unicode=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("public:tag-detail", kwargs={"slug": self.slug})


class Post(models.Model):
    title = models.CharField(max_length=220)
    slug = ContentSlugField(max_length=250, unique=True, allow_unicode=True)
    excerpt = models.CharField(max_length=500, blank=True)
    content = models.TextField(blank=True)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="posts"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="posts"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="posts")

    status = models.CharField(max_length=20, choices=PostStatus.choices, default=PostStatus.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft delete: a trashed post keeps its row (and its status) but is
    # excluded from every public/listing queryset via `deleted_at__isnull`.
    # Only `permanent_delete` (superuser-only) actually removes the row.
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    reading_time = models.PositiveIntegerField(default=0, help_text=_("Minutes, recalculated on save."))
    views_count = models.PositiveIntegerField(default=0)
    allow_comments = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    # SEO foundation — full SEO engine arrives in a later step.
    meta_title = models.CharField(max_length=70, blank=True)
    meta_description = models.CharField(max_length=160, blank=True)
    canonical_url = models.URLField(blank=True)
    robots_index = models.BooleanField(default=True)
    robots_follow = models.BooleanField(default=True)
    og_title = models.CharField(max_length=95, blank=True)
    og_description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        permissions = [
            ("publish_post", "Can publish posts"),
            ("change_any_post", "Can edit posts authored by other users"),
            ("delete_any_post", "Can delete posts authored by other users"),
        ]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status"]),
            models.Index(fields=["published_at"]),
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["author"]),
            models.Index(fields=["category"]),
            models.Index(fields=["status", "published_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_published(self):
        return self.status == PostStatus.PUBLISHED

    @property
    def is_trashed(self):
        return self.deleted_at is not None

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("public:post-detail", kwargs={"slug": self.slug})

    @property
    def word_count(self):
        from .services import plain_text_word_count

        return plain_text_word_count(self.content)

    def compute_reading_time(self):
        from apps.core.models import SiteSetting

        from .services import plain_text_word_count

        words = plain_text_word_count(self.content)
        if not words:
            return 0
        wpm = SiteSetting.load().default_reading_speed_wpm or READING_WPM
        return max(1, round(words / wpm))

    def save(self, *args, **kwargs):
        if not self.slug:
            from .services import unicode_slugify

            self.slug = unicode_slugify(self.title)
        self.reading_time = self.compute_reading_time()
        super().save(*args, **kwargs)


class PostRevision(models.Model):
    """Snapshot of a post's editable content, kept so an accidental edit
    can be reviewed or rolled back. Written by application code only —
    nothing lets a user create or delete these directly.
    """

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="revisions")
    title = models.CharField(max_length=220)
    content = models.TextField(blank=True)
    excerpt = models.CharField(max_length=500, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="post_revisions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        default_permissions = ("view",)
        indexes = [models.Index(fields=["post", "-created_at"])]

    def __str__(self):
        return f"{self.post.title} @ {self.created_at:%Y-%m-%d %H:%M}"


class PostImage(models.Model):
    """Inline content images, uploaded independently of a Post save so the
    editor can insert them mid-draft. `optimized` is a hook for a future
    Celery task to generate WebP/AVIF variants without blocking the save.
    """

    image = models.ImageField(
        upload_to=post_image_upload_path,
        validators=[
            FileExtensionValidator(allowed_extensions=ALLOWED_IMAGE_EXTENSIONS),
            validate_image_size,
        ],
    )
    alt_text = models.CharField(max_length=255, blank=True)
    caption = models.CharField(max_length=255, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    optimized = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_images"
    )
    post = models.ForeignKey(
        Post, on_delete=models.SET_NULL, null=True, blank=True, related_name="images"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.alt_text or self.image.name


class PostViewDaily(models.Model):
    """One row per (post, day) with a running count — the aggregation the
    performance/analytics steps call for, instead of one row per page view
    (which would grow unboundedly with real traffic). `Post.views_count`
    stays the all-time total; this table is what makes "views in the last
    7/30 days" and "Top Posts" possible without scanning a raw-event table.
    """

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="daily_views")
    date = models.DateField()
    views = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]
        constraints = [models.UniqueConstraint(fields=["post", "date"], name="unique_post_view_per_day")]
        indexes = [models.Index(fields=["-date"]), models.Index(fields=["post", "-date"])]

    def __str__(self):
        return f"{self.post_id} — {self.date} ({self.views})"


def _default_preview_expiry():
    from django.utils import timezone

    return timezone.now() + timezone.timedelta(minutes=30)


class PostPreviewToken(models.Model):
    """A shareable, time-limited link to a not-yet-public post — for
    sending a draft to someone without giving them a dashboard login.
    The token itself (not the post ID) is the only thing that grants
    access, so it must never be predictable from the post's ID/slug/time.
    """

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="preview_tokens")
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_preview_tokens"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_preview_expiry)

    class Meta:
        ordering = ["-created_at"]
        default_permissions = ()

    def __str__(self):
        return f"Preview of {self.post_id}, expires {self.expires_at:%Y-%m-%d %H:%M}"

    def is_valid(self):
        from django.utils import timezone

        return timezone.now() < self.expires_at

    @classmethod
    def generate(cls, post, created_by, minutes=30):
        import secrets

        from django.utils import timezone

        return cls.objects.create(
            post=post,
            token=secrets.token_urlsafe(32),
            created_by=created_by,
            expires_at=timezone.now() + timezone.timedelta(minutes=minutes),
        )
