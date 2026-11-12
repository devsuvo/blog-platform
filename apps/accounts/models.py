import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from .managers import UserManager

ALLOWED_AVATAR_EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


def avatar_upload_path(instance, filename):
    """Generate a non-guessable filename so uploads can't collide or leak the original name."""
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"avatars/{uuid.uuid4().hex}.{extension}"


def validate_avatar_size(file):
    if file.size > MAX_AVATAR_SIZE_BYTES:
        raise ValidationError(_("Avatar file size may not exceed 2 MB."))


class UserStatus(models.TextChoices):
    ACTIVE = "active", _("Active")
    INACTIVE = "inactive", _("Inactive")
    SUSPENDED = "suspended", _("Suspended")


class User(AbstractUser):
    """Custom user model. Email is the login identifier; username is kept for public author URLs."""

    email = models.EmailField(_("email address"), unique=True)
    avatar = models.ImageField(
        upload_to=avatar_upload_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=ALLOWED_AVATAR_EXTENSIONS),
            validate_avatar_size,
        ],
    )
    bio = models.TextField(_("bio"), blank=True, max_length=1000)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        return self.get_full_name() or self.username or self.email

    def save(self, *args, **kwargs):
        # `status` is the single source of truth for account access; keep
        # `is_active` in sync so Django's built-in auth backend enforces it
        # automatically without a custom authentication backend.
        self.is_active = self.status == UserStatus.ACTIVE
        super().save(*args, **kwargs)
