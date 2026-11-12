from django.urls import path

from .views import (
    activity_logs,
    categories,
    dashboard,
    exports,
    not_found_logs,
    posts,
    profile,
    redirects,
    roles,
    seo,
    settings,
    system_status,
    tags,
    users,
)

app_name = "dashboard"

urlpatterns = [
    path("", dashboard.index, name="index"),
    path("dashboard/", dashboard.index, name="dashboard"),
    # Posts
    path("posts/", posts.post_list, name="post-list"),
    path("posts/create/", posts.post_create, name="post-create"),
    path("posts/images/upload/", posts.post_image_upload, name="post-image-upload"),
    path("posts/bulk-action/", posts.post_bulk_action, name="post-bulk-action"),
    path("posts/trash/", posts.post_trash_list, name="post-trash-list"),
    path("posts/<int:pk>/", posts.post_edit, name="post-edit"),
    path("posts/<int:pk>/autosave/", posts.post_autosave, name="post-autosave"),
    path("posts/<int:pk>/preview/", posts.post_preview, name="post-preview"),
    path("posts/<int:pk>/preview-link/", posts.post_preview_link_create, name="post-preview-link-create"),
    path("posts/<int:pk>/publish/", posts.post_publish, name="post-publish"),
    path("posts/<int:pk>/schedule/", posts.post_schedule, name="post-schedule"),
    path("posts/<int:pk>/archive/", posts.post_archive, name="post-archive"),
    path("posts/<int:pk>/restore/", posts.post_restore, name="post-restore"),
    path("posts/<int:pk>/delete/", posts.post_delete, name="post-delete"),
    path("posts/<int:pk>/trash/restore/", posts.post_trash_restore, name="post-trash-restore"),
    path("posts/<int:pk>/trash/delete-permanently/", posts.post_permanent_delete, name="post-permanent-delete"),
    path("posts/<int:pk>/duplicate/", posts.post_duplicate, name="post-duplicate"),
    path("posts/<int:pk>/revisions/", posts.post_revisions, name="post-revisions"),
    path("posts/<int:pk>/revisions/<int:revision_pk>/restore/", posts.post_revision_restore, name="post-revision-restore"),
    # Categories
    path("categories/", categories.category_list, name="category-list"),
    path("categories/create/", categories.category_create, name="category-create"),
    path("categories/<int:pk>/edit/", categories.category_edit, name="category-edit"),
    path("categories/<int:pk>/delete/", categories.category_delete, name="category-delete"),
    # Tags
    path("tags/", tags.tag_list, name="tag-list"),
    path("tags/create/", tags.tag_create, name="tag-create"),
    path("tags/merge/", tags.tag_merge, name="tag-merge"),
    path("tags/<int:pk>/edit/", tags.tag_edit, name="tag-edit"),
    path("tags/<int:pk>/delete/", tags.tag_delete, name="tag-delete"),
    # Profile
    path("profile/", profile.profile_view, name="profile"),
    path("profile/password/", profile.profile_password_change, name="profile-password"),
    # Users
    path("users/", users.user_list, name="user-list"),
    path("users/create/", users.user_create, name="user-create"),
    path("users/bulk-action/", users.user_bulk_action, name="user-bulk-action"),
    path("users/<int:pk>/", users.user_detail, name="user-detail"),
    path("users/<int:pk>/edit/", users.user_edit, name="user-edit"),
    path("users/<int:pk>/role/", users.user_change_role, name="user-change-role"),
    path("users/<int:pk>/status/", users.user_change_status, name="user-change-status"),
    path("users/<int:pk>/reset-password/", users.user_reset_password, name="user-reset-password"),
    path("users/<int:pk>/delete/", users.user_delete, name="user-delete"),
    # Roles
    path("roles/", roles.role_list, name="role-list"),
    path("roles/<int:pk>/", roles.role_detail, name="role-detail"),
    # Activity logs
    path("activity-logs/", activity_logs.activity_log_list, name="activity-log-list"),
    path("activity-logs/<int:pk>/", activity_logs.activity_log_detail, name="activity-log-detail"),
    # Settings
    path("settings/", settings.settings_index, name="settings"),
    path("settings/<str:section>/", settings.settings_section, name="settings-section"),
    # Redirects
    path("redirects/", redirects.redirect_list, name="redirect-list"),
    path("redirects/create/", redirects.redirect_create, name="redirect-create"),
    path("redirects/<int:pk>/edit/", redirects.redirect_edit, name="redirect-edit"),
    path("redirects/<int:pk>/delete/", redirects.redirect_delete, name="redirect-delete"),
    # SEO
    path("seo/", seo.seo_dashboard, name="seo-dashboard"),
    # 404 monitoring
    path("404-logs/", not_found_logs.not_found_log_list, name="not-found-log-list"),
    path("404-logs/<int:pk>/dismiss/", not_found_logs.not_found_log_dismiss, name="not-found-log-dismiss"),
    # System status
    path("system/", system_status.system_status, name="system-status"),
    # Exports
    path("posts/export/", exports.export_posts_csv, name="export-posts-csv"),
    path("users/export/", exports.export_users_csv, name="export-users-csv"),
]
