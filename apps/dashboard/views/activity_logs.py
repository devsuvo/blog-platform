from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from apps.core.models import ActivityAction, ActivityLog

User = get_user_model()
PAGE_SIZE = 30


@login_required
@permission_required("core.view_activitylog", raise_exception=True)
def activity_log_list(request):
    logs = ActivityLog.objects.select_related("actor").all()

    user_id = request.GET.get("user", "").strip()
    if user_id.isdigit():
        logs = logs.filter(actor_id=int(user_id))

    action = request.GET.get("action", "").strip()
    if action in ActivityAction.values:
        logs = logs.filter(action=action)

    date_from = request.GET.get("from", "").strip()
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)

    date_to = request.GET.get("to", "").strip()
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    paginator = Paginator(logs, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_title": "Activity Logs",
        "page_obj": page_obj,
        "action_choices": ActivityAction.choices,
        "selected_user": user_id,
        "selected_action": action,
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "admin_panel/activity_logs/list.html", context)


@login_required
@permission_required("core.view_activitylog", raise_exception=True)
def activity_log_detail(request, pk):
    log = get_object_or_404(ActivityLog.objects.select_related("actor", "target_content_type"), pk=pk)
    context = {"page_title": "Activity detail", "log": log}
    return render(request, "admin_panel/activity_logs/detail.html", context)
