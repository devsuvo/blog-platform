from apps.accounts.roles import SUPER_ADMIN, count_active_super_admins


class GuardError(Exception):
    """Raised when a protective rule blocks an admin-panel action. Views
    catch this and turn it into a flash message instead of a 500."""


def ensure_not_self(request, target_user, action_description):
    if target_user.pk == request.user.pk:
        raise GuardError(f"You cannot {action_description} your own account.")


def ensure_super_admin_survives(target_user, removing_super_admin):
    """Block any change that would leave the system with zero active
    Super Admins — e.g. demoting, suspending, deactivating, or deleting
    the last one.
    """
    if removing_super_admin and target_user.is_superuser:
        if count_active_super_admins(exclude_user=target_user) < 1:
            raise GuardError("At least one active Super Admin must remain in the system.")


def ensure_can_assign_role(request, role_name):
    """Only a real Super Admin may grant the Super Admin role — otherwise
    anyone with `accounts.change_user` could promote an accomplice to full
    access.
    """
    if role_name == SUPER_ADMIN and not request.user.is_superuser:
        raise GuardError("Only a Super Admin can grant the Super Admin role.")


def ensure_role_editable(request, group):
    """Only a real Super Admin may edit the Super Admin role's own
    permission set — otherwise a lesser role with `auth.change_group`
    could grant itself Super Admin's permissions.
    """
    if group.name == SUPER_ADMIN and not request.user.is_superuser:
        raise GuardError("Only a Super Admin can modify the Super Admin role.")
