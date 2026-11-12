import csv

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse

from apps.blog.models import Post
from apps.core.models import ActivityAction
from apps.core.services import log_activity

User = get_user_model()


@login_required
@permission_required("blog.view_post", raise_exception=True)
def export_posts_csv(request):
    """Read-only export, scoped by the same ownership rule as the post
    list — an Author exports their own posts, someone with
    `blog.change_any_post` exports everything. Never includes content
    (large, and not what a spreadsheet export is for) or anything secret.
    """
    posts = Post.objects.select_related("author", "category").filter(deleted_at__isnull=True)
    if not (request.user.is_superuser or request.user.has_perm("blog.change_any_post")):
        posts = posts.filter(author=request.user)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="posts.csv"'
    writer = csv.writer(response)
    writer.writerow(["Title", "Slug", "Author", "Category", "Status", "Published At", "Views", "Created At"])
    row_count = 0
    for post in posts.order_by("-created_at"):
        writer.writerow([
            post.title, post.slug, post.author.get_full_name() or post.author.username,
            post.category.name if post.category else "", post.get_status_display(),
            post.published_at.isoformat() if post.published_at else "",
            post.views_count, post.created_at.isoformat(),
        ])
        row_count += 1

    log_activity(
        ActivityAction.POSTS_EXPORTED, actor=request.user,
        description=f"Exported {row_count} post(s) to CSV", request=request,
    )
    return response


@login_required
@permission_required("accounts.view_user", raise_exception=True)
def export_users_csv(request):
    """Never includes password hashes, tokens, or session data — only the
    same fields already visible on the User list/detail pages.
    """
    users = User.objects.prefetch_related("groups").order_by("-date_joined")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="users.csv"'
    writer = csv.writer(response)
    writer.writerow(["Name", "Email", "Username", "Role", "Status", "Joined At", "Last Login"])
    row_count = 0
    for user in users:
        role = user.groups.first()
        writer.writerow([
            user.get_full_name(), user.email, user.username,
            role.name if role else "", user.get_status_display(),
            user.date_joined.isoformat(), user.last_login.isoformat() if user.last_login else "",
        ])
        row_count += 1

    log_activity(
        ActivityAction.USERS_EXPORTED, actor=request.user,
        description=f"Exported {row_count} user(s) to CSV", request=request,
    )
    return response
