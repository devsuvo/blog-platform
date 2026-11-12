from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.core.models import ActivityLog

from ..services import get_dashboard_stats


@login_required
def index(request):
    stats = get_dashboard_stats(request.user)
    recent_activity = ActivityLog.objects.select_related("actor").all()[:8]

    context = {
        "page_title": "Dashboard",
        "stats": stats,
        "recent_activity": recent_activity,
        "can_create_post": request.user.has_perm("blog.add_post"),
    }
    return render(request, "admin_panel/dashboard.html", context)
