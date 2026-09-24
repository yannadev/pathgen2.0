from django.urls import path

from apps.core import admin_views


app_name = "admin_portal"

urlpatterns = [
    path("", admin_views.dashboard, name="dashboard"),
    path("users/", admin_views.users, name="users"),
    path("users/create/", admin_views.user_create, name="user_create"),
    path("users/<uuid:user_id>/<str:action>/", admin_views.user_action, name="user_action"),
    path("classes/", admin_views.classes, name="classes"),
    path("classes/create/", admin_views.class_create, name="class_create"),
    path(
        "classes/<uuid:classroom_id>/<str:action>/",
        admin_views.class_action,
        name="class_action",
    ),
    path(
        "classes/<uuid:classroom_id>/memberships/<uuid:membership_id>/remove/",
        admin_views.membership_remove,
        name="membership_remove",
    ),
    path("overrides/", admin_views.overrides, name="overrides"),
    path("audit/", admin_views.audit_logs, name="audit_logs"),
]
