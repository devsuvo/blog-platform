import unicodedata

from django import forms as django_forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def validate_unicode_slug_with_marks(value):
    """Django's own `validate_unicode_slug` rejects combining marks (Mn/Mc),
    which is exactly what `unicode_slugify()` in services.py intentionally
    keeps so Bangla/Devanagari/etc. vowel signs survive. This validator
    matches what that function actually produces instead of fighting it.
    """
    for ch in value:
        if ch == "-" or ch.isalnum() or unicodedata.category(ch) in ("Mn", "Mc"):
            continue
        raise ValidationError(
            _("Enter a valid slug consisting of Unicode letters, numbers, combining marks, or hyphens."),
            code="invalid",
        )


class ContentSlugFormField(django_forms.CharField):
    default_validators = [validate_unicode_slug_with_marks]


class ContentSlugField(models.SlugField):
    """A SlugField whose validator accepts the output of `unicode_slugify()`.

    Overriding `default_validators` alone isn't enough: `models.SlugField.
    formfield()` hardcodes `forms.SlugField`, which has its own baked-in
    `validate_unicode_slug` regardless of the model field's validators. This
    also overrides `formfield()` so ModelForms get our validator too.
    """

    default_validators = [validate_unicode_slug_with_marks]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # SlugField.__init__ reassigns `self.default_validators` as an
        # instance attribute whenever allow_unicode=True, which shadows the
        # class-level override above — reset it back after calling super().
        self.default_validators = [validate_unicode_slug_with_marks]
        self.validators = list(self.default_validators)

    def formfield(self, **kwargs):
        kwargs.setdefault("form_class", ContentSlugFormField)
        return models.CharField.formfield(self, **kwargs)
