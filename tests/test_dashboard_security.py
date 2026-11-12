from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.roles import ADMIN, AUTHOR, EDITOR, SUPER_ADMIN

from .helpers import DEFAULT_PASSWORD, make_user


class CSRFProtectionTests(TestCase):
    def test_post_without_csrf_token_is_rejected(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        strict_client = Client(enforce_csrf_checks=True)
        strict_client.login(username="super@example.com", password=DEFAULT_PASSWORD)
        target = make_user("target@example.com", "target", role=AUTHOR)

        response = strict_client.post(
            reverse("dashboard:user-change-status", args=[target.pk]),
            {"status": "suspended"},
        )

        self.assertEqual(response.status_code, 403)


class AuthorizationBypassTests(TestCase):
    def test_direct_delete_url_blocked_for_unauthorized_user(self):
        make_user("author@example.com", "author", role=AUTHOR)
        victim = make_user("victim@example.com", "victim", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:user-delete", args=[victim.pk]))
        self.assertEqual(response.status_code, 403)

    def test_direct_role_permission_edit_blocked_for_unauthorized_user(self):
        from django.contrib.auth.models import Group

        make_user("author@example.com", "author", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)
        group = Group.objects.get(name=EDITOR)

        response = self.client.get(reverse("dashboard:role-detail", args=[group.pk]))
        self.assertEqual(response.status_code, 403)


class PrivilegeEscalationTests(TestCase):
    def test_admin_cannot_promote_user_to_super_admin(self):
        admin = make_user("admin@example.com", "admin1", role=ADMIN)
        admin.user_permissions.add(*Permission.objects.filter(content_type__app_label="accounts"))
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)
        target = make_user("target@example.com", "target", role=AUTHOR)

        response = self.client.post(reverse("dashboard:user-change-role", args=[target.pk]), {"role": SUPER_ADMIN})

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.is_superuser)

    def test_admin_cannot_create_super_admin_account(self):
        admin = make_user("admin@example.com", "admin1", role=ADMIN)
        admin.user_permissions.add(*Permission.objects.filter(content_type__app_label="accounts"))
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)

        from django.contrib.auth import get_user_model
        self.client.post(reverse("dashboard:user-create"), {
            "first_name": "Sneaky", "last_name": "One", "email": "sneaky@example.com",
            "username": "sneaky", "bio": "", "status": "active",
            "role": SUPER_ADMIN, "password1": "a-strong-password-456", "password2": "a-strong-password-456",
        })

        self.assertFalse(get_user_model().objects.filter(email="sneaky@example.com").exists())


class RolePermissionMatrixTests(TestCase):
    """Item 45: explicitly test what each role can and cannot reach."""

    def setUp(self):
        self.protected_urls = [
            reverse("dashboard:user-list"),
            reverse("dashboard:role-list"),
            reverse("dashboard:activity-log-list"),
        ]

    def test_super_admin_has_full_access_regardless_of_explicit_permissions(self):
        make_user("super@example.com", "super", role=SUPER_ADMIN)
        self.client.login(username="super@example.com", password=DEFAULT_PASSWORD)

        for url in self.protected_urls:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_admin_access_follows_granted_permissions(self):
        admin = make_user("admin@example.com", "admin1", role=ADMIN)
        self.client.login(username="admin@example.com", password=DEFAULT_PASSWORD)

        # No permissions granted yet -> denied everywhere.
        for url in self.protected_urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

        admin.user_permissions.add(
            Permission.objects.get(codename="view_user", content_type__app_label="accounts")
        )
        response = self.client.get(reverse("dashboard:user-list"))
        self.assertEqual(response.status_code, 200)
        # Still no group/activity-log permission -> still denied there.
        self.assertEqual(self.client.get(reverse("dashboard:role-list")).status_code, 403)

    def test_editor_has_no_user_management_access_by_default(self):
        make_user("editor@example.com", "editor", role=EDITOR)
        self.client.login(username="editor@example.com", password=DEFAULT_PASSWORD)

        for url in self.protected_urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_author_has_no_user_management_access_by_default(self):
        make_user("author@example.com", "author", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        for url in self.protected_urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_sidebar_hides_links_but_routes_stay_protected(self):
        """Menu visibility is a UX nicety, not the security boundary."""
        make_user("author@example.com", "author", role=AUTHOR)
        self.client.login(username="author@example.com", password=DEFAULT_PASSWORD)

        dashboard_response = self.client.get(reverse("dashboard:index"))
        self.assertNotContains(dashboard_response, reverse("dashboard:user-list"))

        direct_response = self.client.get(reverse("dashboard:user-list"))
        self.assertEqual(direct_response.status_code, 403)
