from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.blog.models import Category
from apps.blog.services import category_posts_cache_key, invalidate_category_caches
from apps.core.models import ActivityAction
from apps.core.services import log_activity

from ..forms_blog import CategoryForm


@login_required
@permission_required("blog.view_category", raise_exception=True)
def category_list(request):
    categories = Category.objects.select_related("parent").order_by("name")
    context = {
        "page_title": "Categories",
        "categories": categories,
        "can_create": request.user.has_perm("blog.add_category"),
        "can_edit": request.user.has_perm("blog.change_category"),
        "can_delete": request.user.has_perm("blog.delete_category"),
    }
    return render(request, "admin_panel/categories/list.html", context)


@login_required
@permission_required("blog.add_category", raise_exception=True)
def category_create(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            log_activity(
                ActivityAction.CATEGORY_CREATED, actor=request.user, target=category,
                description=f"Created category '{category.name}'", request=request,
            )
            invalidate_category_caches(category)
            messages.success(request, "Category created.")
            return redirect("dashboard:category-list")
    else:
        form = CategoryForm()
    return render(request, "admin_panel/categories/form.html", {"page_title": "New category", "form": form, "is_create": True})


@login_required
@permission_required("blog.change_category", raise_exception=True)
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    original_slug = category.slug
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            log_activity(
                ActivityAction.CATEGORY_UPDATED, actor=request.user, target=category,
                description=f"Updated category '{category.name}'", request=request,
            )
            if category.slug != original_slug:
                cache.delete(category_posts_cache_key(original_slug))
            invalidate_category_caches(category)
            messages.success(request, "Category updated.")
            return redirect("dashboard:category-list")
    else:
        form = CategoryForm(instance=category)
    return render(request, "admin_panel/categories/form.html", {"page_title": f"Edit {category.name}", "form": form, "is_create": False})


@login_required
@permission_required("blog.delete_category", raise_exception=True)
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    name = category.name
    log_activity(
        ActivityAction.CATEGORY_DELETED, actor=request.user,
        description=f"Deleted category '{name}'", request=request,
    )
    invalidate_category_caches(category)
    category.delete()
    messages.success(request, f"Category '{name}' deleted. Its posts are uncategorized now.")
    return redirect("dashboard:category-list")
