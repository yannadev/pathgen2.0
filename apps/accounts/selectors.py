from __future__ import annotations

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from apps.accounts.models import User
from apps.accounts.permissions import is_admin, is_student, is_teacher


def users_visible_to(actor: User) -> QuerySet[User]:
    queryset = User.objects.all()
    if is_admin(actor):
        return queryset.filter(role__in=[User.Role.TEACHER, User.Role.STUDENT])
    if is_teacher(actor):
        return queryset.filter(
            role=User.Role.STUDENT,
            is_active=True,
            classroom_memberships__left_at__isnull=True,
            classroom_memberships__classroom__teacher=actor,
            classroom_memberships__classroom__status="active",
        ).distinct()
    if is_student(actor):
        return queryset.filter(pk=actor.pk)
    return queryset.none()


def get_visible_user_or_404(*, actor: User, user_id) -> User:
    return get_object_or_404(users_visible_to(actor), pk=user_id)

