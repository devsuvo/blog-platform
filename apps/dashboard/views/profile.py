from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django_ratelimit.decorators import ratelimit

from apps.accounts.roles import get_role
from apps.core.models import ActivityAction
from apps.core.services import log_activity

from ..forms import ProfileForm


@login_required
def profile_view(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            log_activity(ActivityAction.PROFILE_UPDATED, actor=request.user, target=request.user, request=request)
            messages.success(request, "Profile updated.")
            return redirect("dashboard:profile")
    else:
        form = ProfileForm(instance=request.user)

    context = {
        "page_title": "My profile",
        "form": form,
        "role": get_role(request.user),
    }
    return render(request, "admin_panel/profile/profile.html", context)


def _style_password_fields(form):
    for field in form.fields.values():
        field.widget.attrs["class"] = "field-input"
    return form


@login_required
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def profile_password_change(request):
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        _style_password_fields(form)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            log_activity(ActivityAction.PASSWORD_CHANGED, actor=request.user, target=request.user, request=request)
            messages.success(request, "Password changed successfully.")
            return redirect("dashboard:profile")
    else:
        form = _style_password_fields(PasswordChangeForm(user=request.user))

    return render(request, "admin_panel/profile/password.html", {"page_title": "Change password", "form": form})
