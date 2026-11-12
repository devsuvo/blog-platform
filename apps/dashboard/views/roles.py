from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django_ratelimit.decorators import ratelimit

from apps.accounts.roles import ROLE_NAMES
from apps.core.models import ActivityAction
from apps.core.services import log_activity

from ..guards import GuardError, ensure_role_editable
from ..permissions import get_permission_groups

ROLE_DESCRIPTIONS = {
    "Super Admin": "Full, unrestricted access to every area of the platform.",
    "Admin": "Broad administrative access, configurable per permission.",
    "Editor": "Manages content across all authors; typically no user management.",
    "Author": "Manages their own content only.",
    "Contributor": "Can draft their own posts but never publish directly — for guest writers.",
}


@login_required
@permission_required("auth.view_group", raise_exception=True)
def role_list(request):
    roles = Group.objects.filter(name__in=ROLE_NAMES).order_by("name")
    context = {
        "page_title": "Roles",
        "roles": [
            {"group": group, "description": ROLE_DESCRIPTIONS.get(group.name, ""), "member_count": group.user_set.count()}
            for group in roles
        ],
    }
    return render(request, "admin_panel/roles/list.html", context)


@login_required
@permission_required("auth.view_group", raise_exception=True)
@ratelimit(key="user", rate="20/m", method="POST", block=True)
def role_detail(request, pk):
    group = get_object_or_404(Group, pk=pk, name__in=ROLE_NAMES)

    if request.method == "POST":
        try:
            if not request.user.has_perm("auth.change_group"):
                raise GuardError("You do not have permission to change role permissions.")
            ensure_role_editable(request, group)
            submitted_ids = {int(pk_) for pk_ in request.POST.getlist("permissions")}
            valid_ids = set(
                Permission.objects.filter(pk__in=submitted_ids).values_list("pk", flat=True)
            )
            with transaction.atomic():
                group.permissions.set(valid_ids)
            log_activity(
                ActivityAction.PERMISSION_CHANGED,
                actor=request.user,
                target=group,
                description=f"Updated permissions for role {group.name}",
                metadata={"permission_count": len(valid_ids)},
                request=request,
            )
            messages.success(request, f"Permissions for {group.name} updated.")
        except GuardError as exc:
            messages.error(request, str(exc))
        return redirect("dashboard:role-detail", pk=group.pk)

    current_permission_ids = set(group.permissions.values_list("pk", flat=True))
    permission_groups = get_permission_groups()

    context = {
        "page_title": f"Role: {group.name}",
        "role": group,
        "description": ROLE_DESCRIPTIONS.get(group.name, ""),
        "permission_groups": permission_groups,
        "current_permission_ids": current_permission_ids,
        "can_edit": request.user.has_perm("auth.change_group")
        and (group.name != "Super Admin" or request.user.is_superuser),
    }
    return render(request, "admin_panel/roles/detail.html", context)
