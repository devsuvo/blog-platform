"""Object-level authorization for posts.

Django's permission framework (`user.has_perm(...)`) is global — it can't
express "Author X may edit Author X's own drafts but not Author Y's". These
helpers layer that ownership check on top of the model-level `blog.*`
permissions the Roles UI already manages, without a new permission backend.
"""


def can_view_post(user, post):
    return user.is_superuser or user.has_perm("blog.view_post")


def can_edit_post(user, post):
    if user.is_superuser:
        return True
    if not user.has_perm("blog.change_post"):
        return False
    if post.author_id == user.pk:
        return True
    return user.has_perm("blog.change_any_post")


def can_delete_post(user, post):
    if user.is_superuser:
        return True
    if not user.has_perm("blog.delete_post"):
        return False
    if post.author_id == user.pk:
        return True
    return user.has_perm("blog.delete_any_post")


def can_publish_post(user, post):
    if user.is_superuser:
        return True
    if not user.has_perm("blog.publish_post"):
        return False
    if post.author_id == user.pk:
        if _is_author_role_only(user) and not _authors_may_publish():
            return False
        return True
    return user.has_perm("blog.change_any_post")


def _is_author_role_only(user):
    """True only for the plain Author role — Editor/Admin (which also
    typically hold `blog.publish_post`) are never affected by the
    Publishing Settings "allow authors to publish" switch; that switch is
    specifically an Author-role kill-switch, not a global one.
    """
    from apps.accounts.roles import AUTHOR, get_role

    return get_role(user) == AUTHOR


def _authors_may_publish():
    from apps.core.models import SiteSetting

    return SiteSetting.load().allow_authors_to_publish
