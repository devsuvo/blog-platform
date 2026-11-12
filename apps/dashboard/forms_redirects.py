from django import forms
from django.core.exceptions import ValidationError

from apps.public.models import Redirect

TEXT_ATTRS = {"class": "field-input"}


class RedirectForm(forms.ModelForm):
    class Meta:
        model = Redirect
        fields = ["old_path", "new_path", "status_code"]
        widgets = {
            "old_path": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "/blog/old-slug/"}),
            "new_path": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "/blog/new-slug/ or https://…"}),
            "status_code": forms.Select(attrs=TEXT_ATTRS),
        }

    def clean(self):
        cleaned_data = super().clean()
        # Model.clean() carries the real self/reverse/chain-loop validation
        # (it needs both fields normalized together) — re-run it here so
        # form errors surface next to the right fields instead of as a
        # generic 500 when .save() calls full_clean() itself.
        instance = Redirect(
            pk=self.instance.pk,
            old_path=cleaned_data.get("old_path", ""),
            new_path=cleaned_data.get("new_path", ""),
            status_code=cleaned_data.get("status_code") or Redirect._meta.get_field("status_code").default,
        )
        try:
            instance.clean()
        except ValidationError as exc:
            raise forms.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
        cleaned_data["old_path"] = instance.old_path
        cleaned_data["new_path"] = instance.new_path
        return cleaned_data
