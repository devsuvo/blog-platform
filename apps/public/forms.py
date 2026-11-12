from django import forms
from django.utils.html import strip_tags

from .models import ContactMessage

TEXT_ATTRS = {"class": "field-input"}


class ContactForm(forms.ModelForm):
    # Honeypot: invisible to real visitors via CSS, irresistible to bots
    # that blindly fill every field. Any value here means "not human".
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "autocomplete": "off", "tabindex": "-1", "class": "hidden-honeypot",
    }))

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "message"]
        widgets = {
            "name": forms.TextInput(attrs=TEXT_ATTRS),
            "email": forms.EmailInput(attrs=TEXT_ATTRS),
            "subject": forms.TextInput(attrs=TEXT_ATTRS),
            "message": forms.Textarea(attrs={**TEXT_ATTRS, "rows": 6}),
        }

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Spam check failed.")
        return value

    def clean_message(self):
        # Never allow markup through, even escaped-and-displayed-safely —
        # store plain text only.
        return strip_tags(self.cleaned_data.get("message", "")).strip()
