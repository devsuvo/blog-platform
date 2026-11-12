from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.core.models import ActivityAction
from apps.core.services import log_activity
from apps.public.models import Redirect

from ..forms_redirects import RedirectForm

PAGE_SIZE = 25


@login_required
@permission_required("public.view_redirect", raise_exception=True)
def redirect_list(request):
    redirects = Redirect.objects.all()

    query = request.GET.get("q", "").strip()
    if query:
        redirects = redirects.filter(Q(old_path__icontains=query) | Q(new_path__icontains=query))

    paginator = Paginator(redirects, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_title": "Redirects",
        "page_obj": page_obj,
        "query": query,
        "can_create": request.user.has_perm("public.add_redirect"),
        "can_edit": request.user.has_perm("public.change_redirect"),
        "can_delete": request.user.has_perm("public.delete_redirect"),
    }
    return render(request, "admin_panel/redirects/list.html", context)


@login_required
@permission_required("public.add_redirect", raise_exception=True)
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def redirect_create(request):
    if request.method == "POST":
        form = RedirectForm(request.POST)
        if form.is_valid():
            entry = form.save()
            log_activity(
                ActivityAction.REDIRECT_CREATED, actor=request.user, target=entry,
                description=f"Created redirect {entry.old_path} → {entry.new_path}", request=request,
            )
            messages.success(request, "Redirect created.")
            return redirect("dashboard:redirect-list")
    else:
        initial = {}
        old_path = request.GET.get("old_path", "").strip()
        if old_path:
            initial["old_path"] = old_path
        form = RedirectForm(initial=initial)
    return render(request, "admin_panel/redirects/form.html", {"page_title": "New redirect", "form": form, "is_create": True})


@login_required
@permission_required("public.change_redirect", raise_exception=True)
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def redirect_edit(request, pk):
    entry = get_object_or_404(Redirect, pk=pk)
    if request.method == "POST":
        form = RedirectForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            log_activity(
                ActivityAction.REDIRECT_UPDATED, actor=request.user, target=entry,
                description=f"Updated redirect {entry.old_path} → {entry.new_path}", request=request,
            )
            messages.success(request, "Redirect updated.")
            return redirect("dashboard:redirect-list")
    else:
        form = RedirectForm(instance=entry)
    return render(request, "admin_panel/redirects/form.html", {"page_title": "Edit redirect", "form": form, "is_create": False})


@login_required
@permission_required("public.delete_redirect", raise_exception=True)
@ratelimit(key="user", rate="30/m", method="POST", block=True)
@require_POST
def redirect_delete(request, pk):
    entry = get_object_or_404(Redirect, pk=pk)
    description = f"{entry.old_path} → {entry.new_path}"
    log_activity(
        ActivityAction.REDIRECT_DELETED, actor=request.user,
        description=f"Deleted redirect {description}", request=request,
    )
    entry.delete()
    messages.success(request, "Redirect deleted.")
    return redirect("dashboard:redirect-list")
