from django.contrib.auth import views as auth_views
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit


@method_decorator(ratelimit(key="ip", rate="20/m", method="POST", block=True), name="post")
@method_decorator(ratelimit(key="post:username", rate="10/m", method="POST", block=True), name="post")
class RateLimitedLoginView(auth_views.LoginView):
    """Caps login attempts per-IP and per-attempted-email so brute-forcing
    one account can't be done by rotating IPs alone, and hammering one IP
    can't be used to lock out an unrelated victim's email.
    """


@method_decorator(ratelimit(key="post:email", rate="5/m", method="POST", block=True), name="post")
class RateLimitedPasswordResetView(auth_views.PasswordResetView):
    pass
