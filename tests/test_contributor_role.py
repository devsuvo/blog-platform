from django.urls import reverse

from apps.accounts.roles import CONTRIBUTOR, ROLE_NAMES, get_role
from apps.blog.models import PostStatus

from .base import CacheClearingTestCase as TestCase
from .helpers import DEFAULT_PASSWORD, grant_perms, make_post, make_user


class ContributorRoleTests(TestCase):
    def test_contributor_is_a_known_role(self):
        self.assertIn(CONTRIBUTOR, ROLE_NAMES)

    def test_assigning_contributor_role_works(self):
        user = make_user("contributor@example.com", "contrib", role=CONTRIBUTOR)
        self.assertEqual(get_role(user), CONTRIBUTOR)

    def test_contributor_is_not_staff_and_not_superuser(self):
        user = make_user("contributor@example.com", "contrib", role=CONTRIBUTOR)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_contributor_role_appears_in_roles_admin_list(self):
        make_user("contributor@example.com", "contrib", role=CONTRIBUTOR)
        owner = make_user("owner@example.com", "owner")
        grant_perms(owner, "view_group", app_label="auth")
        self.client.login(username="owner@example.com", password=DEFAULT_PASSWORD)

        response = self.client.get(reverse("dashboard:role-list"))

        self.assertContains(response, "Contributor")

    def test_contributor_can_create_own_draft_when_granted_add_post(self):
        user = make_user("contributor@example.com", "contrib", role=CONTRIBUTOR)
        grant_perms(user, "add_post", "change_post", "view_post")
        self.client.login(username="contributor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-create"), {
            "title": "Contributor Draft", "slug": "", "excerpt": "", "content": "<p>Body</p>",
            "category": "", "tags": [],
        })

        self.assertEqual(response.status_code, 302)

    def test_contributor_without_publish_permission_cannot_publish(self):
        user = make_user("contributor@example.com", "contrib", role=CONTRIBUTOR)
        grant_perms(user, "add_post", "change_post", "view_post")  # no publish_post
        post = make_post(user, title="Contributor Post", slug="contributor-post", status=PostStatus.DRAFT)
        self.client.login(username="contributor@example.com", password=DEFAULT_PASSWORD)

        response = self.client.post(reverse("dashboard:post-publish", args=[post.pk]))

        self.assertEqual(response.status_code, 403)
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.DRAFT)

    def test_contributor_cannot_edit_another_contributors_draft(self):
        owner = make_user("owner@example.com", "cowner", role=CONTRIBUTOR)
        grant_perms(owner, "add_post", "change_post", "view_post")
        other = make_user("other@example.com", "cother", role=CONTRIBUTOR)
        grant_perms(other, "add_post", "change_post", "view_post")
        post = make_post(owner, title="Owner Draft", slug="contributor-owner-draft")

        self.client.login(username="other@example.com", password=DEFAULT_PASSWORD)
        response = self.client.post(reverse("dashboard:post-edit", args=[post.pk]), {
            "title": "Hijacked", "slug": "contributor-owner-draft", "content": "<p>x</p>",
        })

        self.assertEqual(response.status_code, 403)
