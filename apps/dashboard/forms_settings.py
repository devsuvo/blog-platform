from django import forms

from apps.core.models import RobotsDefault, SiteSetting

TEXT_ATTRS = {"class": "field-input"}
TEXTAREA_ATTRS = {"class": "field-input", "rows": 3}


class SEOSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = [
            "site_title", "site_name", "site_description",
            "default_meta_description", "default_robots",
            "default_og_title", "default_og_description",
            "twitter_username", "canonical_domain",
        ]
        widgets = {
            "site_title": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "e.g. Python Developer Blog"}),
            "site_name": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "Used in og:site_name / JSON-LD"}),
            "site_description": forms.Textarea(attrs={**TEXTAREA_ATTRS, "rows": 2}),
            "default_meta_description": forms.Textarea(attrs={**TEXTAREA_ATTRS, "rows": 2}),
            "default_robots": forms.Select(attrs=TEXT_ATTRS, choices=RobotsDefault.choices),
            "default_og_title": forms.TextInput(attrs=TEXT_ATTRS),
            "default_og_description": forms.Textarea(attrs={**TEXTAREA_ATTRS, "rows": 2}),
            "twitter_username": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "without the @"}),
            "canonical_domain": forms.URLInput(attrs={**TEXT_ATTRS, "placeholder": "https://example.com"}),
        }

    def clean_twitter_username(self):
        return self.cleaned_data.get("twitter_username", "").lstrip("@").strip()

    def clean_canonical_domain(self):
        value = self.cleaned_data.get("canonical_domain", "").strip()
        if value and not value.startswith(("http://", "https://")):
            raise forms.ValidationError("Include the scheme, e.g. https://example.com")
        return value.rstrip("/")


class GeneralSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["posts_per_page"]
        widgets = {
            "posts_per_page": forms.NumberInput(attrs={**TEXT_ATTRS, "min": 3, "max": 50}),
        }

    def clean_posts_per_page(self):
        value = self.cleaned_data["posts_per_page"]
        if not (3 <= value <= 50):
            raise forms.ValidationError("Choose a number between 3 and 50.")
        return value


class PublishingSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["allow_authors_to_publish", "enable_scheduled_publishing", "default_reading_speed_wpm"]
        widgets = {
            "default_reading_speed_wpm": forms.NumberInput(attrs={**TEXT_ATTRS, "min": 100, "max": 400}),
        }

    def clean_default_reading_speed_wpm(self):
        value = self.cleaned_data["default_reading_speed_wpm"]
        if not (100 <= value <= 400):
            raise forms.ValidationError("Choose a words-per-minute value between 100 and 400.")
        return value


class AnalyticsSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["analytics_enabled", "analytics_retention_days", "track_search"]
        widgets = {
            "analytics_retention_days": forms.NumberInput(attrs={**TEXT_ATTRS, "min": 30, "max": 1825}),
        }

    def clean_analytics_retention_days(self):
        value = self.cleaned_data["analytics_retention_days"]
        if not (30 <= value <= 1825):
            raise forms.ValidationError("Choose a retention period between 30 and 1825 days (5 years).")
        return value


class SocialSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = ["facebook_url", "x_url", "linkedin_url", "github_url", "youtube_url"]
        widgets = {
            "facebook_url": forms.URLInput(attrs={**TEXT_ATTRS, "placeholder": "https://facebook.com/yourpage"}),
            "x_url": forms.URLInput(attrs={**TEXT_ATTRS, "placeholder": "https://x.com/yourhandle"}),
            "linkedin_url": forms.URLInput(attrs={**TEXT_ATTRS, "placeholder": "https://linkedin.com/company/yours"}),
            "github_url": forms.URLInput(attrs={**TEXT_ATTRS, "placeholder": "https://github.com/yourorg"}),
            "youtube_url": forms.URLInput(attrs={**TEXT_ATTRS, "placeholder": "https://youtube.com/@yourchannel"}),
        }
