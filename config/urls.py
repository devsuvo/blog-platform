"""
URL configuration for config project.

`/admin/` is the professional custom Admin Panel (apps.dashboard) — the
front door non-technical staff use daily. Django's own admin site is kept
at `/django-admin/` as a superuser-only emergency/debug tool; it is not
linked from anywhere in the custom panel's navigation.

Public blog URLs (/, /blog/, /category/<slug>/, /tag/<slug>/, /author/<username>/,
/search/, /about/, /contact/, ...) live in apps.public.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("admin/", include("apps.dashboard.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.public.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler400 = "apps.core.views.error_400"
handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
