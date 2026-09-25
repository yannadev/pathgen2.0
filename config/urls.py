"""PathGen root URL configuration."""

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import include, path


def root_redirect(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("/account/login/")
    destinations = {
        "admin": "/manage/",
        "teacher": "/teacher/",
        "student": "/student/",
    }
    return redirect(destinations.get(request.user.role, "/account/"))


urlpatterns = [
    path("", root_redirect, name="root"),
    path("admin/", admin.site.urls),
    path("manage/content/", include("apps.curriculum.urls")),
    path("manage/", include("apps.core.admin_urls")),
    path("teacher/", include("apps.classrooms.urls")),
    path("student/", include("apps.learning.urls")),
    path("account/", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
]
