from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import ADMIN, AUTHOR, EDITOR, SUPER_ADMIN

from .helpers import DEFAULT_PASSWORD, make_user


def user_permissions():
    return Permission.objects.filter(content_type__app_label="accounts")


class RoleAssignmentTests(TestCase):
    def test_role_assignment_works(self):
        super_admin = make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)
        target = make_user("target@example.com", "target", role=AUTHOR)

        response = self.client.post(reverse("dashboard:user-change-role", args=[target.pk]), {"role": EDITOR})

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(list(target.groups.values_list("name", flat=True)), [EDITOR])


class PermissionAssignmentTests(TestCase):
    def setUp(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)
        self.editor_group = Group.objects.get(name=EDITOR)

    def test_permission_assignment_works(self):
        perm = user_permissions().get(codename="view_user")

        response = self.client.post(reverse("dashboard:role-detail", args=[self.editor_group.pk]), {
            "permissions": [perm.pk],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.editor_group.permissions.values_list("pk", flat=True)), [perm.pk])

    def test_unauthorized_permission_changes_fail(self):
        make_user("author@example.com", "author", role=AUTHOR)
        self.client.logout()
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        perm = user_permissions().get(codename="view_user")

        response = self.client.post(reverse("dashboard:role-detail", args=[self.editor_group.pk]), {
            "permissions": [perm.pk],
        })

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.editor_group.permissions.count(), 0)


class SuperAdminRoleProtectionTests(TestCase):
    def test_non_superuser_admin_cannot_edit_super_admin_role(self):
        admin = make_user("admin@example.com", "admin1", role=ADMIN)
        admin.user_permissions.add(*Permission.objects.filter(content_type__app_label="auth"))
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)

        super_group = Group.objects.get(name=SUPER_ADMIN)
        perm = user_permissions().get(codename="delete_user")

        response = self.client.post(reverse("dashboard:role-detail", args=[super_group.pk]), {
            "permissions": [perm.pk],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(super_group.permissions.count(), 0)

    def test_superuser_can_edit_super_admin_role(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

        super_group = Group.objects.get(name=SUPER_ADMIN)
        perm = user_permissions().get(codename="view_user")

        response = self.client.post(reverse("dashboard:role-detail", args=[super_group.pk]), {
            "permissions": [perm.pk],
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(super_group.permissions.values_list("pk", flat=True)), [perm.pk])
