from __future__ import annotations

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.accounts.permissions import is_admin, is_student, is_teacher
from apps.classrooms.models import Classroom


def classrooms_visible_to(actor: User) -> QuerySet[Classroom]:
    queryset = Classroom.objects.all()
    if is_admin(actor):
        return queryset
    if is_teacher(actor):
        return queryset.filter(teacher=actor, status=Classroom.Status.ACTIVE)
    if is_student(actor):
        return queryset.filter(
            status=Classroom.Status.ACTIVE,
            student_memberships__student=actor,
            student_memberships__left_at__isnull=True,
        ).distinct()
    return queryset.none()


def get_visible_classroom_or_404(*, actor: User, classroom_id) -> Classroom:
    return get_object_or_404(classrooms_visible_to(actor), pk=classroom_id)

