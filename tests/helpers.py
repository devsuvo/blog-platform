from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission

from apps.accounts.roles import set_role

User = get_user_model()
DEFAULT_PASSWORD = "a-strong-password-123"


def make_user(email, username, role=None, password=DEFAULT_PASSWORD, **extra):
    user = User.objects.create_user(email=email, username=username, password=password, **extra)
    if role:
        set_role(user, role)
    return user


def grant_perms(user, *codenames, app_label="blog"):
    perms = Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames)
    user.user_permissions.add(*perms)
    return user


def make_post(author, title="Test Post", content="<p>Hello world</p>", **extra):
    from apps.blog.models import Post

    return Post.objects.create(author=author, title=title, content=content, **extra)
