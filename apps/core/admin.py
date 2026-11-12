from django.contrib import admin

from .models import ActivityLog, NotFoundLog, SiteSetting


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor", "action", "description", "ip_address"]
    list_filter = ["action"]
    search_fields = ["description", "actor__email", "actor__username"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteSetting)
class SiteSettingAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSetting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotFoundLog)
class NotFoundLogAdmin(admin.ModelAdmin):
    list_display = ["path", "hit_count", "referrer", "first_seen", "last_seen"]
    search_fields = ["path", "referrer"]
    ordering = ["-hit_count"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
