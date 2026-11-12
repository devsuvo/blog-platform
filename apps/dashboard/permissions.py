from django.contrib.auth.models import Permission

# Category -> (app_label, model) backing real Django permissions.
# Categories mapped to None don't have a model yet (Posts/Categories/... ship
# in later steps); the Roles UI shows them as "coming soon" rather than
# fabricating permissions that don't gate anything.
PERMISSION_CATEGORIES = [
    ("Posts", ("blog", "post")),
    ("Categories", ("blog", "category")),
    ("Tags", ("blog", "tag")),
    ("Comments", None),
    ("SEO", ("core", "sitesetting")),
    ("Redirects", ("public", "redirect")),
    ("Analytics", None),
    ("Users", ("accounts", "user")),
    ("Roles", ("auth", "group")),
    ("Settings", None),
    ("System", ("core", "activitylog")),
]


def get_permission_groups():
    """Permission categories for the role-editing screen: real, persisted
    Permission objects for models that exist today, an empty/placeholder
    entry for the rest.
    """
    groups = []
    for label, target in PERMISSION_CATEGORIES:
        if target is None:
            groups.append({"label": label, "available": False, "permissions": []})
            continue
        app_label, model = target
        perms = list(
            Permission.objects.filter(
                content_type__app_label=app_label, content_type__model=model
            ).order_by("codename")
        )
        groups.append({"label": label, "available": True, "permissions": perms})
    return groups
