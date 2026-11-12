from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse


class AccountStatusMiddleware:
    """Ends the session the moment an authenticated user's account stops
    being ACTIVE (deactivated or suspended mid-session), instead of only
    blocking a fresh login. Centralized here so no view needs to repeat
    this check.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.is_active:
            logout(request)
            messages.error(request, "Your account is no longer active. Please contact an administrator.")
            return redirect(reverse("accounts:login"))
        return self.get_response(request)
