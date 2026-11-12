from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordResetForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from apps.accounts.models import UserStatus
from apps.accounts.roles import ROLE_NAMES, get_role, set_role
from apps.core.models import ActivityAction
from apps.core.services import log_activity

from ..forms import BulkUserActionForm, RoleAssignForm, StatusChangeForm, UserCreateForm, UserUpdateForm
from ..guards import GuardError, ensure_can_assign_role, ensure_not_self, ensure_super_admin_survives

User = get_user_model()
PAGE_SIZE = 25


@login_required
@permission_required("accounts.view_user", raise_exception=True)
def user_list(request):
    users = User.objects.all().prefetch_related("groups").order_by("-date_joined")

    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(
            Q(email__icontains=query)
            | Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    role = request.GET.get("role", "").strip()
    if role in ROLE_NAMES:
        users = users.filter(groups__name=role)

    status = request.GET.get("status", "").strip()
    if status in UserStatus.values:
        users = users.filter(status=status)

    paginator = Paginator(users, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_title": "Users",
        "page_obj": page_obj,
        "query": query,
        "selected_role": role,
        "selected_status": status,
        "role_choices": ROLE_NAMES,
        "status_choices": UserStatus.choices,
        "can_create": request.user.has_perm("accounts.add_user"),
        "can_edit": request.user.has_perm("accounts.change_user"),
        "can_delete": request.user.has_perm("accounts.delete_user"),
    }
    return render(request, "admin_panel/users/list.html", context)


@login_required
@permission_required("accounts.view_user", raise_exception=True)
def user_detail(request, pk):
    user = get_object_or_404(User.objects.prefetch_related("groups"), pk=pk)
    context = {
        "page_title": user.get_full_name() or user.email,
        "target_user": user,
        "role": get_role(user),
        "role_choices": ROLE_NAMES,
        "status_choices": UserStatus.choices,
        "is_self": user.pk == request.user.pk,
        "can_edit": request.user.has_perm("accounts.change_user"),
        "can_delete": request.user.has_perm("accounts.delete_user"),
        "recent_activity": user.activity_logs.all()[:10],
    }
    return render(request, "admin_panel/users/detail.html", context)


@login_required
@permission_required("accounts.add_user", raise_exception=True)
@ratelimit(key="user", rate="20/m", method="POST", block=True)
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                ensure_can_assign_role(request, form.cleaned_data["role"])
            except GuardError as exc:
                messages.error(request, str(exc))
                return render(request, "admin_panel/users/form.html", {"page_title": "Create user", "form": form, "is_create": True})
            with transaction.atomic():
                user = form.save()
                set_role(user, form.cleaned_data["role"])
            log_activity(
                ActivityAction.USER_CREATED,
                actor=request.user,
                target=user,
                description=f"Created user {user.email}",
                metadata={"role": form.cleaned_data["role"], "status": user.status},
                request=request,
            )
            messages.success(request, f"User {user.email} created successfully.")
            return redirect("dashboard:user-detail", pk=user.pk)
    else:
        form = UserCreateForm()

    return render(request, "admin_panel/users/form.html", {"page_title": "Create user", "form": form, "is_create": True})


@login_required
@permission_required("accounts.change_user", raise_exception=True)
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = UserUpdateForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            log_activity(
                ActivityAction.USER_UPDATED,
                actor=request.user,
                target=user,
                description=f"Updated user {user.email}",
                request=request,
            )
            messages.success(request, "User updated successfully.")
            return redirect("dashboard:user-detail", pk=user.pk)
    else:
        form = UserUpdateForm(instance=user)

    context = {"page_title": f"Edit {user.email}", "form": form, "target_user": user, "is_create": False}
    return render(request, "admin_panel/users/form.html", context)


@login_required
@permission_required("accounts.change_user", raise_exception=True)
@require_POST
@ratelimit(key="user", rate="20/m", method="POST", block=True)
def user_change_role(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = RoleAssignForm(request.POST)
    if form.is_valid():
        new_role = form.cleaned_data["role"]
        old_role = get_role(user)
        try:
            ensure_not_self(request, user, "change the role of")
            ensure_can_assign_role(request, new_role)
            ensure_super_admin_survives(user, removing_super_admin=new_role != "Super Admin")
            with transaction.atomic():
                set_role(user, new_role)
            log_activity(
                ActivityAction.ROLE_CHANGED,
                actor=request.user,
                target=user,
                description=f"Changed role of {user.email}: {old_role} → {new_role}",
                metadata={"from_role": old_role, "to_role": new_role},
                request=request,
            )
            messages.success(request, f"Role updated to {new_role}.")
        except GuardError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Invalid role selection.")
    return redirect("dashboard:user-detail", pk=user.pk)


@login_required
@permission_required("accounts.change_user", raise_exception=True)
@require_POST
def user_change_status(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = StatusChangeForm(request.POST)
    if form.is_valid():
        new_status = form.cleaned_data["status"]
        old_status = user.status
        try:
            ensure_not_self(request, user, "change the status of")
            ensure_super_admin_survives(user, removing_super_admin=new_status != UserStatus.ACTIVE)
            user.status = new_status
            user.save(update_fields=["status", "is_active"])
            log_activity(
                ActivityAction.STATUS_CHANGED,
                actor=request.user,
                target=user,
                description=f"Changed status of {user.email}: {old_status} → {new_status}",
                metadata={"from_status": old_status, "to_status": new_status},
                request=request,
            )
            messages.success(request, f"Status updated to {user.get_status_display()}.")
        except GuardError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Invalid status selection.")
    return redirect("dashboard:user-detail", pk=user.pk)


@login_required
@permission_required("accounts.delete_user", raise_exception=True)
@require_POST
def user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    try:
        ensure_not_self(request, user, "delete")
        ensure_super_admin_survives(user, removing_super_admin=True)
        email = user.email
        with transaction.atomic():
            log_activity(
                ActivityAction.USER_DELETED,
                actor=request.user,
                description=f"Deleted user {email}",
                request=request,
            )
            user.delete()
        messages.success(request, f"User {email} deleted.")
        return redirect("dashboard:user-list")
    except GuardError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:user-detail", pk=pk)


@login_required
@permission_required("accounts.change_user", raise_exception=True)
@require_POST
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = PasswordResetForm({"email": user.email})
    if form.is_valid():
        form.save(request=request)
        log_activity(
            ActivityAction.PASSWORD_RESET_REQUESTED,
            actor=request.user,
            target=user,
            description=f"Sent password reset email to {user.email}",
            request=request,
        )
        messages.success(request, f"Password reset email sent to {user.email}.")
    else:
        messages.error(request, "Could not send a password reset email for this account.")
    return redirect("dashboard:user-detail", pk=user.pk)


@login_required
@permission_required("accounts.change_user", raise_exception=True)
@require_POST
def user_bulk_action(request):
    form = BulkUserActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid bulk action request.")
        return redirect("dashboard:user-list")

    action = form.cleaned_data["action"]
    target_status = {
        "activate": UserStatus.ACTIVE,
        "deactivate": UserStatus.INACTIVE,
        "suspend": UserStatus.SUSPENDED,
    }[action]

    updated, skipped = 0, 0
    users = User.objects.filter(pk__in=form.cleaned_data["user_ids"])
    with transaction.atomic():
        for user in users:
            if user.pk == request.user.pk:
                skipped += 1
                continue
            if target_status != UserStatus.ACTIVE and user.is_superuser:
                try:
                    ensure_super_admin_survives(user, removing_super_admin=True)
                except GuardError:
                    skipped += 1
                    continue
            old_status = user.status
            user.status = target_status
            user.save(update_fields=["status", "is_active"])
            log_activity(
                ActivityAction.STATUS_CHANGED,
                actor=request.user,
                target=user,
                description=f"Bulk changed status of {user.email}: {old_status} → {target_status}",
                metadata={"from_status": old_status, "to_status": target_status, "bulk": True},
                request=request,
            )
            updated += 1

    if updated:
        messages.success(request, f"Updated {updated} user(s).")
    if skipped:
        messages.warning(request, f"Skipped {skipped} user(s) (your own account or the last active Super Admin).")
    return redirect("dashboard:user-list")
