from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.blog.models import Post, Tag
from apps.blog.services import invalidate_tag_caches, tag_posts_cache_key
from apps.core.models import ActivityAction
from apps.core.services import log_activity

from ..forms_blog import TagForm, TagMergeForm


@login_required
@permission_required("blog.view_tag", raise_exception=True)
def tag_list(request):
    tags = Tag.objects.order_by("name")
    context = {
        "page_title": "Tags",
        "tags": tags,
        "can_create": request.user.has_perm("blog.add_tag"),
        "can_edit": request.user.has_perm("blog.change_tag"),
        "can_delete": request.user.has_perm("blog.delete_tag"),
    }
    return render(request, "admin_panel/tags/list.html", context)


@login_required
@permission_required("blog.add_tag", raise_exception=True)
def tag_create(request):
    if request.method == "POST":
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save()
            log_activity(
                ActivityAction.TAG_CREATED, actor=request.user, target=tag,
                description=f"Created tag '{tag.name}'", request=request,
            )
            invalidate_tag_caches(tag)
            messages.success(request, "Tag created.")
            return redirect("dashboard:tag-list")
    else:
        form = TagForm()
    return render(request, "admin_panel/tags/form.html", {"page_title": "New tag", "form": form, "is_create": True})


@login_required
@permission_required("blog.change_tag", raise_exception=True)
def tag_edit(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    original_slug = tag.slug
    if request.method == "POST":
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            log_activity(
                ActivityAction.TAG_UPDATED, actor=request.user, target=tag,
                description=f"Updated tag '{tag.name}'", request=request,
            )
            if tag.slug != original_slug:
                cache.delete(tag_posts_cache_key(original_slug))
            invalidate_tag_caches(tag)
            messages.success(request, "Tag updated.")
            return redirect("dashboard:tag-list")
    else:
        form = TagForm(instance=tag)
    return render(request, "admin_panel/tags/form.html", {"page_title": f"Edit {tag.name}", "form": form, "is_create": False})


@login_required
@permission_required("blog.delete_tag", raise_exception=True)
@require_POST
def tag_delete(request, pk):
    tag = get_object_or_404(Tag, pk=pk)
    name = tag.name
    log_activity(
        ActivityAction.TAG_DELETED, actor=request.user,
        description=f"Deleted tag '{name}'", request=request,
    )
    invalidate_tag_caches(tag)
    tag.delete()
    messages.success(request, f"Tag '{name}' deleted.")
    return redirect("dashboard:tag-list")


@login_required
@permission_required("blog.change_tag", raise_exception=True)
@permission_required("blog.delete_tag", raise_exception=True)
def tag_merge(request):
    if request.method == "POST":
        form = TagMergeForm(request.POST)
        if form.is_valid():
            source_tags = list(form.cleaned_data["source_tags"])
            target = form.cleaned_data["target_tag"]

            with transaction.atomic():
                # `Post.tags.add()` is safe against duplicates at the DB
                # level (the through table's own unique constraint), so a
                # post already carrying both a source tag and the target
                # doesn't end up with a duplicate relationship.
                affected_post_ids = list(
                    Post.objects.filter(tags__in=source_tags).values_list("pk", flat=True).distinct()
                )
                for post in Post.objects.filter(pk__in=affected_post_ids):
                    post.tags.add(target)

                source_names = [tag.name for tag in source_tags]
                for tag in source_tags:
                    cache.delete(tag_posts_cache_key(tag.slug))
                    tag.delete()

            invalidate_tag_caches(target)
            log_activity(
                ActivityAction.TAG_MERGED, actor=request.user, target=target,
                description=f"Merged tag(s) {', '.join(source_names)} into '{target.name}'",
                metadata={"source_tags": source_names, "target_tag": target.name, "posts_affected": len(affected_post_ids)},
                request=request,
            )
            messages.success(request, f"Merged {len(source_names)} tag(s) into '{target.name}'.")
            return redirect("dashboard:tag-list")
    else:
        form = TagMergeForm()
    return render(request, "admin_panel/tags/merge.html", {"page_title": "Merge Tags", "form": form})
