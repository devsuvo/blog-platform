from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import NotFoundLog

PAGE_SIZE = 50


@login_required
@permission_required("core.view_notfoundlog", raise_exception=True)
def not_found_log_list(request):
    logs = NotFoundLog.objects.order_by("-hit_count", "-last_seen")
    paginator = Paginator(logs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_title": "404 Monitoring",
        "page_obj": page_obj,
        "can_delete": request.user.has_perm("core.delete_notfoundlog"),
    }
    return render(request, "admin_panel/not_found_logs/list.html", context)


@login_required
@permission_required("core.delete_notfoundlog", raise_exception=True)
@require_POST
def not_found_log_dismiss(request, pk):
    NotFoundLog.objects.filter(pk=pk).delete()
    messages.success(request, "Dismissed.")
    return redirect("dashboard:not-found-log-list")
