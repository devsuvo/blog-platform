from django.contrib.auth.models import Group
from django.db import transaction

SUPER_ADMIN = "Super Admin"
ADMIN = "Admin"
EDITOR = "Editor"
AUTHOR = "Author"
CONTRIBUTOR = "Contributor"

ROLE_NAMES = [SUPER_ADMIN, ADMIN, EDITOR, AUTHOR, CONTRIBUTOR]

# Roles that receive Django admin (staff) access in addition to the custom panel.
STAFF_ROLES = {SUPER_ADMIN, ADMIN}


def get_role(user):
    """Return the user's single role-group name, or None if unassigned."""
    role = user.groups.filter(name__in=ROLE_NAMES).values_list("name", flat=True).first()
    return role


def count_active_super_admins(exclude_user=None):
    from .models import User, UserStatus

    qs = User.objects.filter(is_superuser=True, status=UserStatus.ACTIVE)
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    return qs.count()


@transaction.atomic
def set_role(user, role_name):
    """Assign `user` to exactly one of the four role groups, syncing the
    `is_superuser` / `is_staff` flags Django's permission system actually
    enforces. Group membership alone never grants superuser bypass, so the
    two must be kept in sync here rather than left to drift.
    """
    if role_name not in ROLE_NAMES:
        raise ValueError(f"Unknown role: {role_name}")

    user.groups.remove(*Group.objects.filter(name__in=ROLE_NAMES))
    group, _created = Group.objects.get_or_create(name=role_name)
    user.groups.add(group)

    user.is_superuser = role_name == SUPER_ADMIN
    user.is_staff = role_name in STAFF_ROLES
    user.save(update_fields=["is_superuser", "is_staff"])
    return group
