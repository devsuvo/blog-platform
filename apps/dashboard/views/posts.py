import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.blog.models import Category, Post, PostImage, PostPreviewToken, PostRevision, PostStatus
from apps.blog.permissions import can_delete_post, can_edit_post, can_publish_post, can_view_post
from apps.blog.sanitizer import sanitize_post_html
from apps.blog.services import analyze_post_seo, generate_unique_slug, invalidate_post_caches
from apps.core.models import ActivityAction
from apps.core.services import log_activity
from apps.public.services import record_slug_redirect

from ..forms_blog import BulkPostActionForm, PostForm, ScheduleForm
from ..services import invalidate_dashboard_stats

PAGE_SIZE = 20
REVISION_CAP = 20


def _record_slug_change_redirect(old_slug, new_slug):
    old_path = reverse("public:post-detail", kwargs={"slug": old_slug})
    new_path = reverse("public:post-detail", kwargs={"slug": new_slug})
    record_slug_redirect(old_path, new_path)


def _post_queryset_for(user, include_trashed=False):
    queryset = Post.objects.select_related("author", "category").prefetch_related("tags")
    if not include_trashed:
        queryset = queryset.filter(deleted_at__isnull=True)
    if user.is_superuser or user.has_perm("blog.change_any_post"):
        return queryset
    return queryset.filter(author=user)


def _snapshot_revision(post, editor, title=None, content=None, excerpt=None):
    PostRevision.objects.create(
        post=post,
        title=post.title if title is None else title,
        content=post.content if content is None else content,
        excerpt=post.excerpt if excerpt is None else excerpt,
        author=editor,
    )
    stale_ids = list(post.revisions.values_list("pk", flat=True)[REVISION_CAP:])
    if stale_ids:
        PostRevision.objects.filter(pk__in=stale_ids).delete()


@login_required
@permission_required("blog.view_post", raise_exception=True)
def post_list(request):
    posts = _post_queryset_for(request.user)

    query = request.GET.get("q", "").strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query) | Q(slug__icontains=query) | Q(content__icontains=query)
        )

    status = request.GET.get("status", "").strip()
    if status in PostStatus.values:
        posts = posts.filter(status=status)

    category_id = request.GET.get("category", "").strip()
    if category_id.isdigit():
        posts = posts.filter(category_id=int(category_id))

    author_id = request.GET.get("author", "").strip()
    if author_id.isdigit():
        posts = posts.filter(author_id=int(author_id))

    paginator = Paginator(posts, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_title": "Posts",
        "page_obj": page_obj,
        "query": query,
        "selected_status": status,
        "selected_category": category_id,
        "status_choices": PostStatus.choices,
        "categories": Category.objects.all(),
        "can_create": request.user.has_perm("blog.add_post"),
        "can_bulk_edit": request.user.has_perm("blog.change_post"),
        "can_view_trash": request.user.has_perm("blog.delete_post"),
    }
    return render(request, "admin_panel/posts/list.html", context)


@login_required
@permission_required("blog.add_post", raise_exception=True)
def post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.status = PostStatus.DRAFT
            with transaction.atomic():
                post.save()
                form.save_m2m()
            log_activity(
                ActivityAction.POST_CREATED, actor=request.user, target=post,
                description=f"Created post '{post.title}'", request=request,
            )
            invalidate_dashboard_stats(author=post.author)
            messages.success(request, "Draft saved.")
            return redirect("dashboard:post-edit", pk=post.pk)
    else:
        form = PostForm()

    return render(request, "admin_panel/posts/form.html", {
        "page_title": "New post", "form": form, "is_create": True,
    })


@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post.objects.select_related("author", "category"), pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied
    if post.is_trashed:
        messages.error(request, "This post is in the trash — restore it first to make changes.")
        return redirect("dashboard:post-trash-list")

    if request.method == "POST":
        # Capture before binding the form: ModelForm.is_valid() mutates
        # `post` in place via construct_instance(), so comparing against
        # it afterwards would always see the new values on both sides.
        original_title, original_content, original_excerpt = post.title, post.content, post.excerpt
        original_slug = post.slug
        was_published = post.is_published
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            content_changed = form.cleaned_data["content"] != original_content or form.cleaned_data["title"] != original_title
            slug_changed = form.cleaned_data.get("slug") != original_slug
            with transaction.atomic():
                if content_changed:
                    _snapshot_revision(
                        post, request.user,
                        title=original_title, content=original_content, excerpt=original_excerpt,
                    )
                form.save()
                if slug_changed and was_published:
                    _record_slug_change_redirect(original_slug, post.slug)
            log_activity(
                ActivityAction.POST_UPDATED, actor=request.user, target=post,
                description=f"Updated post '{post.title}'", request=request,
            )
            invalidate_post_caches(post, previous_slug=original_slug if slug_changed else None)
            messages.success(request, "Post updated.")
            return redirect("dashboard:post-edit", pk=post.pk)
    else:
        form = PostForm(instance=post)

    from apps.core.models import SiteSetting

    context = {
        "page_title": f"Edit: {post.title}",
        "form": form,
        "post": post,
        "is_create": False,
        "can_publish": can_publish_post(request.user, post),
        "can_delete": can_delete_post(request.user, post),
        "schedule_form": ScheduleForm(),
        "seo_checks": analyze_post_seo(post),
        "scheduling_enabled": SiteSetting.load().enable_scheduled_publishing,
    }
    return render(request, "admin_panel/posts/form.html", context)


@login_required
@ratelimit(key="user", rate="60/m", method="POST", block=True)
@require_POST
def post_autosave(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied
    if post.status not in (PostStatus.DRAFT, PostStatus.SCHEDULED):
        return JsonResponse({"saved": False, "reason": "Autosave is disabled for this status."}, status=409)

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"saved": False, "reason": "Invalid payload."}, status=400)

    title = (payload.get("title") or "").strip()
    if title:
        post.title = title[:220]
    post.excerpt = (payload.get("excerpt") or "")[:500]
    post.content = sanitize_post_html(payload.get("content") or "")
    post.save(update_fields=["title", "excerpt", "content", "reading_time", "updated_at"])

    return JsonResponse({"saved": True, "saved_at": timezone.now().isoformat()})


@login_required
def post_preview(request, pk):
    post = get_object_or_404(Post.objects.select_related("author", "category").prefetch_related("tags"), pk=pk)
    if not can_view_post(request.user, post) and post.author_id != request.user.pk:
        raise PermissionDenied
    return render(request, "admin_panel/posts/preview.html", {"page_title": post.title, "post": post})


@login_required
@permission_required("blog.publish_post", raise_exception=True)
@require_POST
def post_publish(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_publish_post(request.user, post):
        raise PermissionDenied

    post.status = PostStatus.PUBLISHED
    if post.published_at is None:
        post.published_at = timezone.now()
    post.scheduled_at = None
    post.save(update_fields=["status", "published_at", "scheduled_at", "updated_at"])

    log_activity(
        ActivityAction.POST_PUBLISHED, actor=request.user, target=post,
        description=f"Published post '{post.title}'", request=request,
    )
    invalidate_post_caches(post)
    invalidate_dashboard_stats(author=post.author)
    messages.success(request, "Post published.")
    return redirect("dashboard:post-edit", pk=post.pk)


@login_required
@permission_required("blog.publish_post", raise_exception=True)
@require_POST
def post_schedule(request, pk):
    from apps.core.models import SiteSetting

    post = get_object_or_404(Post, pk=pk)
    if not can_publish_post(request.user, post):
        raise PermissionDenied
    if not SiteSetting.load().enable_scheduled_publishing:
        messages.error(request, "Scheduled publishing is disabled in Settings.")
        return redirect("dashboard:post-edit", pk=post.pk)

    form = ScheduleForm(request.POST)
    if form.is_valid():
        post.status = PostStatus.SCHEDULED
        post.scheduled_at = form.cleaned_data["scheduled_at"]
        post.save(update_fields=["status", "scheduled_at", "updated_at"])
        log_activity(
            ActivityAction.POST_SCHEDULED, actor=request.user, target=post,
            description=f"Scheduled post '{post.title}' for {post.scheduled_at:%Y-%m-%d %H:%M}",
            request=request,
        )
        invalidate_dashboard_stats(author=post.author)
        messages.success(request, "Post scheduled.")
    else:
        messages.error(request, " ".join(form.errors.get("scheduled_at", ["Invalid schedule time."])))
    return redirect("dashboard:post-edit", pk=post.pk)


@login_required
@require_POST
def post_archive(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied

    post.status = PostStatus.ARCHIVED
    post.save(update_fields=["status", "updated_at"])
    log_activity(
        ActivityAction.POST_ARCHIVED, actor=request.user, target=post,
        description=f"Archived post '{post.title}'", request=request,
    )
    invalidate_post_caches(post)
    invalidate_dashboard_stats(author=post.author)
    messages.success(request, "Post archived.")
    return redirect("dashboard:post-list")


@login_required
@require_POST
def post_restore(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied
    if post.status != PostStatus.ARCHIVED:
        messages.error(request, "Only archived posts can be restored.")
        return redirect("dashboard:post-edit", pk=post.pk)

    post.status = PostStatus.DRAFT
    post.save(update_fields=["status", "updated_at"])
    log_activity(
        ActivityAction.POST_RESTORED, actor=request.user, target=post,
        description=f"Restored post '{post.title}' to draft", request=request,
    )
    invalidate_dashboard_stats(author=post.author)
    messages.success(request, "Post restored to draft.")
    return redirect("dashboard:post-edit", pk=post.pk)


@login_required
@require_POST
def post_delete(request, pk):
    """Moves a post to Trash (soft delete) rather than removing the row —
    see `post_permanent_delete` for the actual, superuser-only, irreversible
    deletion. Keeping the same URL/view name a "Delete" button already
    pointed at means nothing upstream had to change to get the safety net.
    """
    post = get_object_or_404(Post, pk=pk)
    if not can_delete_post(request.user, post):
        raise PermissionDenied
    if post.is_trashed:
        messages.info(request, f"'{post.title}' is already in the trash.")
        return redirect("dashboard:post-trash-list")

    post.deleted_at = timezone.now()
    post.save(update_fields=["deleted_at"])
    invalidate_post_caches(post)
    invalidate_dashboard_stats(author=post.author)
    log_activity(
        ActivityAction.POST_TRASHED, actor=request.user, target=post,
        description=f"Moved post '{post.title}' to trash", request=request,
    )
    messages.success(request, f"'{post.title}' moved to trash.")
    return redirect("dashboard:post-list")


def _trash_queryset_for(user):
    queryset = Post.objects.select_related("author", "category").filter(deleted_at__isnull=False)
    if user.is_superuser or user.has_perm("blog.change_any_post"):
        return queryset
    return queryset.filter(author=user)


@login_required
@permission_required("blog.delete_post", raise_exception=True)
def post_trash_list(request):
    posts = _trash_queryset_for(request.user).order_by("-deleted_at")
    paginator = Paginator(posts, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    context = {
        "page_title": "Trash",
        "page_obj": page_obj,
        "can_permanently_delete": request.user.is_superuser,
    }
    return render(request, "admin_panel/posts/trash.html", context)


@login_required
@require_POST
def post_trash_restore(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_delete_post(request.user, post):
        raise PermissionDenied
    if not post.is_trashed:
        messages.error(request, "This post isn't in the trash.")
        return redirect("dashboard:post-trash-list")

    post.deleted_at = None
    post.save(update_fields=["deleted_at"])
    invalidate_post_caches(post)
    invalidate_dashboard_stats(author=post.author)
    log_activity(
        ActivityAction.POST_RESTORED_FROM_TRASH, actor=request.user, target=post,
        description=f"Restored post '{post.title}' from trash", request=request,
    )
    messages.success(request, f"'{post.title}' restored from trash.")
    return redirect("dashboard:post-trash-list")


@login_required
@require_POST
def post_permanent_delete(request, pk):
    """Irreversible — restricted to superusers, and only ever reachable
    for a post that's already sitting in the trash, so nothing can be
    permanently destroyed in a single click from the normal post list.
    """
    if not request.user.is_superuser:
        raise PermissionDenied

    post = get_object_or_404(Post, pk=pk)
    if not post.is_trashed:
        messages.error(request, "Move this post to trash first before permanently deleting it.")
        return redirect("dashboard:post-list")

    title = post.title
    invalidate_post_caches(post)
    invalidate_dashboard_stats(author=post.author)
    log_activity(
        ActivityAction.POST_PERMANENTLY_DELETED, actor=request.user,
        description=f"Permanently deleted post '{title}'", request=request,
    )
    post.delete()
    messages.success(request, f"'{title}' permanently deleted.")
    return redirect("dashboard:post-trash-list")


@login_required
@permission_required("blog.add_post", raise_exception=True)
@require_POST
def post_duplicate(request, pk):
    """Creates a new draft copy owned by the person duplicating it.
    Deliberately does NOT copy published_at/scheduled_at/canonical_url —
    a duplicate is a fresh draft, not a second copy of a live URL.
    """
    source = get_object_or_404(Post, pk=pk)
    if not can_view_post(request.user, source) and source.author_id != request.user.pk:
        raise PermissionDenied

    new_title = f"{source.title} (copy)"
    duplicate = Post.objects.create(
        title=new_title,
        slug=generate_unique_slug(Post, new_title),
        excerpt=source.excerpt,
        content=source.content,
        author=request.user,
        category=source.category,
        status=PostStatus.DRAFT,
        allow_comments=source.allow_comments,
        meta_title=source.meta_title,
        meta_description=source.meta_description,
        robots_index=source.robots_index,
        robots_follow=source.robots_follow,
        og_title=source.og_title,
        og_description=source.og_description,
    )
    duplicate.tags.set(source.tags.all())

    log_activity(
        ActivityAction.POST_DUPLICATED, actor=request.user, target=duplicate,
        description=f"Duplicated post '{source.title}' as '{duplicate.title}'", request=request,
    )
    invalidate_dashboard_stats(author=request.user)
    messages.success(request, f"Duplicated as a new draft: '{duplicate.title}'.")
    return redirect("dashboard:post-edit", pk=duplicate.pk)


@login_required
@require_POST
def post_preview_link_create(request, pk):
    """Generates a shareable, expiring, token-based preview link — for
    sending a draft to someone without giving them a dashboard login.
    See apps.public.views.preview for the token-authorized public view.
    """
    post = get_object_or_404(Post, pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied

    token = PostPreviewToken.generate(post, created_by=request.user)
    preview_url = request.build_absolute_uri(reverse("public:token-preview", args=[token.token]))

    log_activity(
        ActivityAction.PREVIEW_LINK_CREATED, actor=request.user, target=post,
        description=f"Created a preview link for '{post.title}'", request=request,
    )
    messages.success(request, f"Preview link created (expires in 30 minutes): {preview_url}")
    return redirect("dashboard:post-edit", pk=post.pk)


@login_required
@permission_required("blog.change_post", raise_exception=True)
@require_POST
def post_bulk_action(request):
    form = BulkPostActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid bulk action request.")
        return redirect("dashboard:post-list")

    action = form.cleaned_data["action"]
    posts = _post_queryset_for(request.user).filter(pk__in=form.cleaned_data["post_ids"])

    updated, skipped = 0, 0
    with transaction.atomic():
        for post in posts:
            allowed, new_status = _bulk_action_permission_and_status(request.user, post, action)
            if not allowed:
                skipped += 1
                continue

            if action == "change_category":
                post.category = form.cleaned_data["category"]
                post.save(update_fields=["category", "updated_at"])
            else:
                post.status = new_status
                update_fields = ["status", "updated_at"]
                if action == "publish":
                    if post.published_at is None:
                        post.published_at = timezone.now()
                        update_fields.append("published_at")
                    post.scheduled_at = None
                    update_fields.append("scheduled_at")
                elif action == "trash":
                    post.deleted_at = timezone.now()
                    update_fields = ["deleted_at", "updated_at"]
                post.save(update_fields=update_fields)

            invalidate_post_caches(post)
            invalidate_dashboard_stats(author=post.author)
            log_activity(
                ActivityAction.POST_UPDATED, actor=request.user, target=post,
                description=f"Bulk {action} on post '{post.title}'", metadata={"bulk": True, "action": action},
                request=request,
            )
            updated += 1

    if updated:
        messages.success(request, f"Updated {updated} post(s).")
    if skipped:
        messages.warning(request, f"Skipped {skipped} post(s) — you don't have permission for that action on them.")
    return redirect("dashboard:post-list")


def _bulk_action_permission_and_status(user, post, action):
    """Returns (allowed, new_status). Every action is still checked with
    the same per-post ownership rules as the single-post endpoints — a
    bulk action is never a way around object-level permissions.
    """
    if action == "publish":
        return can_publish_post(user, post), PostStatus.PUBLISHED
    if action == "unpublish":
        return can_edit_post(user, post), PostStatus.DRAFT
    if action == "archive":
        return can_edit_post(user, post), PostStatus.ARCHIVED
    if action == "trash":
        return can_delete_post(user, post), None
    if action == "change_category":
        return can_edit_post(user, post), None
    return False, None


@login_required
def post_revisions(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied
    revisions = post.revisions.select_related("author")
    return render(request, "admin_panel/posts/revisions.html", {
        "page_title": f"Revisions: {post.title}", "post": post, "revisions": revisions,
    })


@login_required
@require_POST
def post_revision_restore(request, pk, revision_pk):
    post = get_object_or_404(Post, pk=pk)
    if not can_edit_post(request.user, post):
        raise PermissionDenied
    revision = get_object_or_404(PostRevision, pk=revision_pk, post=post)

    with transaction.atomic():
        _snapshot_revision(post, request.user)
        post.title = revision.title
        post.content = revision.content
        post.excerpt = revision.excerpt
        post.save(update_fields=["title", "content", "excerpt", "reading_time", "updated_at"])

    log_activity(
        ActivityAction.REVISION_RESTORED, actor=request.user, target=post,
        description=f"Restored revision from {revision.created_at:%Y-%m-%d %H:%M}", request=request,
    )
    invalidate_post_caches(post)
    messages.success(request, "Revision restored.")
    return redirect("dashboard:post-edit", pk=post.pk)


@login_required
@permission_required("blog.add_post", raise_exception=True)
@ratelimit(key="user", rate="30/m", method="POST", block=True)
@require_POST
def post_image_upload(request):
    from PIL import Image as PILImage
    from PIL import UnidentifiedImageError

    file = request.FILES.get("file")
    if not file:
        return JsonResponse({"error": "No file provided."}, status=400)

    image = PostImage(uploaded_by=request.user, alt_text=request.POST.get("alt", "")[:255])
    image.image = file
    try:
        image.full_clean()
    except Exception:
        return JsonResponse({"error": "Invalid image (check type and size)."}, status=400)

    # Extension/MIME allowlisting alone doesn't prove the bytes are really
    # an image — decode it before trusting it enough to save.
    try:
        with PILImage.open(file) as im:
            im.verify()
        file.seek(0)
        with PILImage.open(file) as im:
            width, height = im.size
        file.seek(0)
    except (UnidentifiedImageError, OSError):
        return JsonResponse({"error": "File is not a valid image."}, status=400)

    image.width, image.height = width, height
    image.save()

    return JsonResponse({
        "url": image.image.url, "id": image.pk, "width": image.width, "height": image.height,
    })
