def admin_panel(request):
    """Sidebar visibility flags. These only hide/show links — every route
    they point to re-checks the same permission server-side.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {
        "nav_can_view_users": user.has_perm("accounts.view_user"),
        "nav_can_view_roles": user.has_perm("auth.view_group"),
        "nav_can_view_activity_logs": user.has_perm("core.view_activitylog"),
        "nav_can_view_settings": user.is_staff,
        "nav_can_view_seo": user.is_staff,
        "nav_can_view_redirects": user.has_perm("public.view_redirect"),
        "nav_can_view_404_logs": user.has_perm("core.view_notfoundlog"),
        "nav_can_view_system_status": user.is_superuser,
    }
