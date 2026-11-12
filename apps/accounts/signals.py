from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

from apps.core.models import ActivityAction
from apps.core.services import log_activity


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    log_activity(ActivityAction.LOGIN, actor=user, target=user, request=request)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    if user is not None:
        log_activity(ActivityAction.LOGOUT, actor=user, target=user, request=request)


@receiver(user_login_failed)
def on_user_login_failed(sender, credentials, request=None, **kwargs):
    attempted_email = credentials.get("username", "")
    log_activity(
        ActivityAction.LOGIN_FAILED,
        actor=None,
        description=f"Failed login attempt for {attempted_email}"[:255],
        request=request,
    )
