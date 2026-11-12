from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserStatus
from apps.accounts.roles import ADMIN, AUTHOR, SUPER_ADMIN
from apps.core.models import ActivityLog

from .helpers import DEFAULT_PASSWORD, make_user

User = get_user_model()


class UserCreateTests(TestCase):
    def setUp(self):
        self.super_admin = make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

    def test_authorized_admin_can_create_user(self):
        response = self.client.post(reverse("dashboard:user-create"), {
            "first_name": "New", "last_name": "Writer", "email": "writer@example.com",
            "username": "writer", "bio": "", "status": UserStatus.ACTIVE,
            "role": AUTHOR, "password1": "a-strong-password-456", "password2": "a-strong-password-456",
        })

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="writer@example.com")
        self.assertTrue(user.check_password("a-strong-password-456"))
        self.assertEqual(ActivityLog.objects.filter(action="user_created").count(), 1)

    def test_duplicate_email_rejected(self):
        make_user("existing@example.com", "existing")

        response = self.client.post(reverse("dashboard:user-create"), {
            "first_name": "Dup", "last_name": "User", "email": "existing@example.com",
            "username": "dupuser", "bio": "", "status": UserStatus.ACTIVE,
            "role": AUTHOR, "password1": "a-strong-password-456", "password2": "a-strong-password-456",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_non_superuser_cannot_create_super_admin(self):
        admin = make_user("admin@example.com", "admin1", role=ADMIN)
        admin.user_permissions.add(*self._user_perms())
        self.client.logout()
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:user-create"), {
            "first_name": "Sneaky", "last_name": "Admin", "email": "sneaky@example.com",
            "username": "sneaky", "bio": "", "status": UserStatus.ACTIVE,
            "role": SUPER_ADMIN, "password1": "a-strong-password-456", "password2": "a-strong-password-456",
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="sneaky@example.com").exists())

    @staticmethod
    def _user_perms():
        from django.contrib.auth.models import Permission
        return Permission.objects.filter(content_type__app_label="accounts")


class UnauthorizedUserCreateTests(TestCase):
    def test_unauthorized_user_cannot_create_user(self):
        make_user("author@example.com", "author", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:user-create"))
        self.assertEqual(response.status_code, 403)

        response = self.client.post(reverse("dashboard:user-create"), {})
        self.assertEqual(response.status_code, 403)


class UserEditTests(TestCase):
    def setUp(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)
        self.target = make_user("target@example.com", "target", role=AUTHOR)

    def test_user_can_be_edited(self):
        response = self.client.post(reverse("dashboard:user-edit", args=[self.target.pk]), {
            "first_name": "Updated", "last_name": "Name", "email": "target@example.com",
            "username": "target", "bio": "Updated bio",
        })

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.first_name, "Updated")

    def test_status_can_be_changed(self):
        response = self.client.post(reverse("dashboard:user-change-status", args=[self.target.pk]), {
            "status": UserStatus.SUSPENDED,
        })

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, UserStatus.SUSPENDED)
        self.assertFalse(self.target.is_active)


class UnauthorizedDeletionTests(TestCase):
    def test_unauthorized_deletion_blocked(self):
        make_user("author@example.com", "author", role=AUTHOR)
        target = make_user("victim@example.com", "victim", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:user-delete", args=[target.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=target.pk).exists())


class SuperAdminProtectionTests(TestCase):
    def setUp(self):
        self.super_admin = make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

    def test_cannot_change_own_status(self):
        response = self.client.post(reverse("dashboard:user-change-status", args=[self.super_admin.pk]), {
            "status": UserStatus.SUSPENDED,
        })
        self.assertEqual(response.status_code, 302)
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.status, UserStatus.ACTIVE)

    def test_cannot_change_own_role(self):
        response = self.client.post(reverse("dashboard:user-change-role", args=[self.super_admin.pk]), {
            "role": AUTHOR,
        })
        self.assertEqual(response.status_code, 302)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_superuser)

    def test_cannot_delete_self(self):
        response = self.client.post(reverse("dashboard:user-delete", args=[self.super_admin.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.super_admin.pk).exists())

    def test_last_super_admin_cannot_be_demoted_by_another_admin(self):
        from django.contrib.auth.models import Permission

        other_admin = make_user("other@example.com", "otheradmin", role=ADMIN)
        other_admin.user_permissions.add(
            Permission.objects.get(codename="change_user", content_type__app_label="accounts")
        )
        self.client.logout()
        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:user-change-role", args=[self.super_admin.pk]), {
            "role": AUTHOR,
        })

        self.assertEqual(response.status_code, 302)
        self.super_admin.refresh_from_db()
        self.assertTrue(self.super_admin.is_superuser)

    def test_last_super_admin_can_be_demoted_when_another_exists(self):
        second_admin = make_user("second@example.com", "second", role=SUPER_ADMIN)
        self.client.logout()
        self.client.login(username="second@example.com", password=DEFAULT_PASSWORD)

        third = make_user("third@example.com", "third", role=AUTHOR)
        response = self.client.post(reverse("dashboard:user-change-role", args=[third.pk]), {
            "role": SUPER_ADMIN,
        })
        self.assertEqual(response.status_code, 302)

    def test_last_super_admin_cannot_be_deleted(self):
        response = self.client.post(reverse("dashboard:user-delete", args=[self.super_admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.super_admin.pk).exists())


class BulkActionTests(TestCase):
    def setUp(self):
        self.super_admin = make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)
        self.u1 = make_user("u1@example.com", "u1", role=AUTHOR)
        self.u2 = make_user("u2@example.com", "u2", role=AUTHOR)

    def test_bulk_suspend_updates_selected_users(self):
        response = self.client.post(reverse("dashboard:user-bulk-action"), {
            "action": "suspend",
            "user_ids": f"{self.u1.pk},{self.u2.pk}",
        })

        self.assertEqual(response.status_code, 302)
        self.u1.refresh_from_db()
        self.u2.refresh_from_db()
        self.assertEqual(self.u1.status, UserStatus.SUSPENDED)
        self.assertEqual(self.u2.status, UserStatus.SUSPENDED)

    def test_bulk_action_skips_self(self):
        response = self.client.post(reverse("dashboard:user-bulk-action"), {
            "action": "suspend",
            "user_ids": f"{self.u1.pk},{self.super_admin.pk}",
        })

        self.assertEqual(response.status_code, 302)
        self.super_admin.refresh_from_db()
        self.assertEqual(self.super_admin.status, UserStatus.ACTIVE)
