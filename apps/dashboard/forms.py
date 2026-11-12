from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import UserStatus
from apps.accounts.roles import ROLE_NAMES

User = get_user_model()

TEXT_INPUT_ATTRS = {"class": "field-input"}
FILE_INPUT_ATTRS = {"class": "block w-full text-sm text-slate-600 dark:text-slate-300"}


class UserCreateForm(forms.ModelForm):
    role = forms.ChoiceField(choices=[(name, name) for name in ROLE_NAMES], widget=forms.Select(attrs=TEXT_INPUT_ATTRS))
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs=TEXT_INPUT_ATTRS))
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs=TEXT_INPUT_ATTRS))

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "username", "bio", "avatar", "status"]
        widgets = {
            "first_name": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "last_name": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "email": forms.EmailInput(attrs=TEXT_INPUT_ATTRS),
            "username": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "bio": forms.Textarea(attrs={**TEXT_INPUT_ATTRS, "rows": 3}),
            "avatar": forms.ClearableFileInput(attrs=FILE_INPUT_ATTRS),
            "status": forms.Select(attrs=TEXT_INPUT_ATTRS),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        if password2:
            validate_password(password2)
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "username", "bio", "avatar"]
        widgets = {
            "first_name": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "last_name": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "email": forms.EmailInput(attrs=TEXT_INPUT_ATTRS),
            "username": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "bio": forms.Textarea(attrs={**TEXT_INPUT_ATTRS, "rows": 3}),
            "avatar": forms.ClearableFileInput(attrs=FILE_INPUT_ATTRS),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "bio", "avatar"]
        widgets = {
            "first_name": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "last_name": forms.TextInput(attrs=TEXT_INPUT_ATTRS),
            "email": forms.EmailInput(attrs=TEXT_INPUT_ATTRS),
            "bio": forms.Textarea(attrs={**TEXT_INPUT_ATTRS, "rows": 3}),
            "avatar": forms.ClearableFileInput(attrs=FILE_INPUT_ATTRS),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email


class RoleAssignForm(forms.Form):
    role = forms.ChoiceField(choices=[(name, name) for name in ROLE_NAMES])


class StatusChangeForm(forms.Form):
    status = forms.ChoiceField(choices=UserStatus.choices)


class BulkUserActionForm(forms.Form):
    ACTIONS = [("activate", "Activate"), ("deactivate", "Deactivate"), ("suspend", "Suspend")]

    action = forms.ChoiceField(choices=ACTIONS)
    user_ids = forms.CharField()

    def clean_user_ids(self):
        raw = self.cleaned_data["user_ids"]
        try:
            ids = [int(value) for value in raw.split(",") if value.strip()]
        except ValueError:
            raise forms.ValidationError("Invalid user selection.")
        if not ids:
            raise forms.ValidationError("Select at least one user.")
        return ids
