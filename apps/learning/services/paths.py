from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.permissions import is_student
from apps.curriculum.models import Lesson

from ..models import StudentPath


def _require_active_student(student: User) -> None:
    if not is_student(student):
        raise PermissionDenied


@transaction.atomic
def ensure_student_path(*, student: User) -> StudentPath:
    _require_active_student(student)
    path = StudentPath.objects.select_for_update().filter(student=student).first()
    if path is not None:
        return path
    return StudentPath.objects.create(
        student=student,
        status=StudentPath.Status.PRETEST_REQUIRED,
        current_lesson=None,
        current_stage=StudentPath.Stage.PRETEST,
    )


@transaction.atomic
def complete_lesson_content(*, student: User, lesson: Lesson) -> StudentPath:
    _require_active_student(student)
    path = StudentPath.objects.select_for_update().get(student=student)
    if (
        path.status != StudentPath.Status.LEARNING
        or path.current_stage != StudentPath.Stage.LESSON
        or path.current_lesson_id != lesson.pk
        or not lesson.is_published
    ):
        raise ValidationError("This lesson is not the current learning step.")
    path.current_stage = StudentPath.Stage.REGULAR
    path.save(update_fields=["current_stage", "updated_at"])
    return path
