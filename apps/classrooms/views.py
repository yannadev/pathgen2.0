from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.accounts.permissions import teacher_required
from apps.classrooms.selectors import classrooms_visible_to, get_visible_classroom_or_404


@never_cache
@teacher_required
@require_safe
def my_classes(request: HttpRequest) -> HttpResponse:
    classrooms = classrooms_visible_to(request.user).order_by("code")
    return render(
        request,
        "teacher/my_class.html",
        {
            "classrooms": classrooms,
            "breadcrumbs": [("", "My Classes")],
        },
    )


@never_cache
@teacher_required
@require_safe
def class_detail(request: HttpRequest, classroom_id) -> HttpResponse:
    classroom = get_visible_classroom_or_404(
        actor=request.user,
        classroom_id=classroom_id,
    )
    memberships = classroom.student_memberships.filter(left_at__isnull=True).select_related(
        "student"
    ).order_by("student__last_name", "student__first_name", "student__username")
    return render(
        request,
        "teacher/class_detail.html",
        {
            "classroom": classroom,
            "memberships": memberships,
            "breadcrumbs": [
                (reverse_my_classes(), "My Classes"),
                ("", classroom.code),
            ],
        },
    )


def reverse_my_classes() -> str:
    from django.urls import reverse

    return reverse("teacher:my_classes")
