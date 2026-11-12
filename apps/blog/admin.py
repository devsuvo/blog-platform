from django.contrib import admin

from .models import Category, Post, PostImage, PostRevision, Tag


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ["title", "author", "category", "status", "published_at", "updated_at", "views_count"]
    list_filter = ["status", "category"]
    search_fields = ["title", "slug", "content"]
    autocomplete_fields = ["author", "category"]
    readonly_fields = ["reading_time", "views_count", "created_at", "updated_at"]
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(PostRevision)
class PostRevisionAdmin(admin.ModelAdmin):
    list_display = ["post", "author", "created_at"]
    readonly_fields = [f.name for f in PostRevision._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PostImage)
class PostImageAdmin(admin.ModelAdmin):
    list_display = ["id", "post", "alt_text", "uploaded_by", "optimized", "created_at"]
    list_filter = ["optimized"]
