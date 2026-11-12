from django.contrib import admin

from .models import ContactMessage, Redirect


@admin.register(Redirect)
class RedirectAdmin(admin.ModelAdmin):
    list_display = ["old_path", "new_path", "status_code", "is_auto", "updated_at"]
    list_filter = ["status_code", "is_auto"]
    search_fields = ["old_path", "new_path"]


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["subject", "name", "email", "created_at"]
    search_fields = ["name", "email", "subject", "message"]
    readonly_fields = ["name", "email", "subject", "message", "ip_address", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
