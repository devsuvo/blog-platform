from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "username", "get_full_name", "status", "is_staff", "is_superuser", "date_joined"]
    list_filter = ["status", "is_staff", "is_superuser", "is_active"]
    search_fields = ["email", "username", "first_name", "last_name"]
    readonly_fields = ["date_joined", "last_login"]

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "avatar", "bio")}),
        ("Status & permissions", {
            "fields": ("status", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2", "status", "is_staff", "is_superuser"),
        }),
    )
