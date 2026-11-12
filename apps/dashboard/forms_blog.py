from django import forms
from django.utils import timezone

from apps.blog.models import Category, Post, Tag
from apps.blog.sanitizer import sanitize_post_html
from apps.blog.services import generate_unique_slug

TEXT_ATTRS = {"class": "field-input"}
TEXTAREA_ATTRS = {"class": "field-input", "rows": 3}


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = [
            "title", "slug", "excerpt", "content", "category", "tags",
            "allow_comments", "is_featured",
            "meta_title", "meta_description", "canonical_url",
            "robots_index", "robots_follow", "og_title", "og_description",
        ]
        widgets = {
            "title": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "Post title"}),
            "slug": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "auto-generated-from-title"}),
            "excerpt": forms.Textarea(attrs={**TEXTAREA_ATTRS, "placeholder": "Short summary shown on listings and as a meta-description fallback"}),
            "content": forms.Textarea(attrs={"class": "hidden", "id": "content-raw"}),
            "category": forms.Select(attrs=TEXT_ATTRS),
            "tags": forms.SelectMultiple(attrs={**TEXT_ATTRS, "size": 6}),
            "meta_title": forms.TextInput(attrs=TEXT_ATTRS),
            "meta_description": forms.Textarea(attrs={**TEXTAREA_ATTRS, "rows": 2}),
            "canonical_url": forms.URLInput(attrs=TEXT_ATTRS),
            "og_title": forms.TextInput(attrs=TEXT_ATTRS),
            "og_description": forms.Textarea(attrs={**TEXTAREA_ATTRS, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["content"].required = True

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Title is required.")
        return title

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        title = self.data.get("title", "") or self.cleaned_data.get("title", "")
        if not slug:
            slug = generate_unique_slug(Post, title, instance_pk=self.instance.pk)
            return slug
        queryset = Post.objects.exclude(pk=self.instance.pk) if self.instance.pk else Post.objects.all()
        if queryset.filter(slug=slug).exists():
            raise forms.ValidationError("This slug is already in use.")
        return slug

    def clean_content(self):
        return sanitize_post_html(self.cleaned_data.get("content", ""))

    def clean_canonical_url(self):
        value = self.cleaned_data.get("canonical_url", "").strip()
        if not value:
            return value
        lowered = value.lower()
        if any(marker in lowered for marker in ("javascript:", "data:", "vbscript:")):
            raise forms.ValidationError("That doesn't look like a safe URL.")
        if not lowered.startswith(("http://", "https://")):
            raise forms.ValidationError("Canonical URL must start with http:// or https://.")
        return value


class BulkPostActionForm(forms.Form):
    ACTIONS = [
        ("publish", "Publish"),
        ("unpublish", "Unpublish (back to draft)"),
        ("archive", "Archive"),
        ("trash", "Move to trash"),
        ("change_category", "Change category"),
    ]

    action = forms.ChoiceField(choices=ACTIONS)
    post_ids = forms.CharField()
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=False)

    def clean_post_ids(self):
        raw = self.cleaned_data["post_ids"]
        try:
            ids = [int(value) for value in raw.split(",") if value.strip()]
        except ValueError:
            raise forms.ValidationError("Invalid post selection.")
        if not ids:
            raise forms.ValidationError("Select at least one post.")
        return ids

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("action") == "change_category" and not cleaned_data.get("category"):
            self.add_error("category", "Select a category for the Change Category action.")
        return cleaned_data


class ScheduleForm(forms.Form):
    scheduled_at = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={**TEXT_ATTRS, "type": "datetime-local"}),
    )

    def clean_scheduled_at(self):
        value = self.cleaned_data["scheduled_at"]
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        if value <= timezone.now():
            raise forms.ValidationError("Scheduled time must be in the future. Use Publish for immediate publishing.")
        return value


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "description", "parent", "meta_title", "meta_description"]
        widgets = {
            "name": forms.TextInput(attrs=TEXT_ATTRS),
            "slug": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "auto-generated-from-name"}),
            "description": forms.Textarea(attrs=TEXTAREA_ATTRS),
            "parent": forms.Select(attrs=TEXT_ATTRS),
            "meta_title": forms.TextInput(attrs=TEXT_ATTRS),
            "meta_description": forms.Textarea(attrs={**TEXTAREA_ATTRS, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        name = self.data.get("name", "") or self.cleaned_data.get("name", "")
        if not slug:
            return generate_unique_slug(Category, name, instance_pk=self.instance.pk)
        queryset = Category.objects.exclude(pk=self.instance.pk) if self.instance.pk else Category.objects.all()
        if queryset.filter(slug=slug).exists():
            raise forms.ValidationError("This slug is already in use.")
        return slug

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and self.instance.pk:
            node = parent
            while node is not None:
                if node.pk == self.instance.pk:
                    raise forms.ValidationError("A category cannot be its own ancestor.")
                node = node.parent
        return parent


class TagMergeForm(forms.Form):
    source_tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(), widget=forms.SelectMultiple(attrs={**TEXT_ATTRS, "size": 8}),
        help_text="Every post tagged with any of these gets re-tagged with the target below; these tags are then deleted.",
    )
    target_tag = forms.ModelChoiceField(queryset=Tag.objects.all(), widget=forms.Select(attrs=TEXT_ATTRS))

    def clean(self):
        cleaned_data = super().clean()
        source_tags = cleaned_data.get("source_tags")
        target_tag = cleaned_data.get("target_tag")
        if source_tags and target_tag and target_tag in source_tags:
            self.add_error("target_tag", "The target tag can't also be one of the source tags being merged away.")
        return cleaned_data


class TagForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "slug"]
        widgets = {
            "name": forms.TextInput(attrs=TEXT_ATTRS),
            "slug": forms.TextInput(attrs={**TEXT_ATTRS, "placeholder": "auto-generated-from-name"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip()
        name = self.data.get("name", "") or self.cleaned_data.get("name", "")
        if not slug:
            return generate_unique_slug(Tag, name, instance_pk=self.instance.pk)
        queryset = Tag.objects.exclude(pk=self.instance.pk) if self.instance.pk else Tag.objects.all()
        if queryset.filter(slug=slug).exists():
            raise forms.ValidationError("This slug is already in use.")
        return slug
