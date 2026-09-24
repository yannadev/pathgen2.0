from __future__ import annotations

from collections.abc import Iterable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import is_admin
from apps.classrooms.models import Classroom, StudentMembership
from apps.core.services.audit import record_audit_event, record_model_audit_event


def _require_admin(actor: User) -> None:
    if not is_admin(actor):
        raise PermissionDenied


def _locked_active_teacher(teacher: User | None) -> User | None:
    if teacher is None:
        return None
    locked = User.objects.select_for_update().get(pk=teacher.pk)
    if locked.role != User.Role.TEACHER or not locked.is_active:
        raise ValidationError("Select an active teacher account.")
    return locked


def _locked_active_student(student: User) -> User:
    locked = User.objects.select_for_update().get(pk=student.pk)
    if locked.role != User.Role.STUDENT or not locked.is_active:
        raise ValidationError("Select an active student account.")
    return locked


@transaction.atomic
def create_classroom(
    *, actor: User, code: str, name: str, teacher: User | None = None
) -> Classroom:
    _require_admin(actor)
    normalized_code = code.strip()
    normalized_name = name.strip()
    if not normalized_code or not normalized_name:
        raise ValidationError("Class code and name are required.")
    assigned_teacher = _locked_active_teacher(teacher)
    classroom = Classroom(code=normalized_code, name=normalized_name, teacher=assigned_teacher)
    classroom.full_clean()
    classroom.save()
    record_model_audit_event(
        actor=actor,
        action="class.created",
        target=classroom,
        target_snapshot={"code": classroom.code, "status": classroom.status},
        metadata={"teacher_id": str(assigned_teacher.pk) if assigned_teacher else None},
    )
    return classroom


@transaction.atomic
def update_classroom(*, actor: User, classroom: Classroom, code: str, name: str) -> Classroom:
    _require_admin(actor)
    locked = Classroom.objects.select_for_update().get(pk=classroom.pk)
    if locked.status != Classroom.Status.ACTIVE:
        raise ValidationError("Reactivate this class before editing it.")
    normalized_code = code.strip()
    normalized_name = name.strip()
    if not normalized_code or not normalized_name:
        raise ValidationError("Class code and name are required.")
    changed_fields = []
    for field, value in (("code", normalized_code), ("name", normalized_name)):
        if getattr(locked, field) != value:
            setattr(locked, field, value)
            changed_fields.append(field)
    if not changed_fields:
        return locked
    locked.full_clean()
    locked.save(update_fields=[*changed_fields, "updated_at"])
    record_model_audit_event(
        actor=actor,
        action="class.updated",
        target=locked,
        target_snapshot={"code": locked.code, "status": locked.status},
        metadata={"changed_fields": changed_fields},
    )
    return locked


@transaction.atomic
def assign_teacher(
    *, actor: User, classroom: Classroom, teacher: User | None
) -> Classroom:
    _require_admin(actor)
    locked = Classroom.objects.select_for_update().get(pk=classroom.pk)
    if locked.status != Classroom.Status.ACTIVE:
        raise ValidationError("Teachers can be assigned only to active classes.")
    assigned_teacher = _locked_active_teacher(teacher)
    previous_id = locked.teacher_id
    next_id = assigned_teacher.pk if assigned_teacher else None
    if previous_id == next_id:
        return locked
    locked.teacher = assigned_teacher
    locked.save(update_fields=["teacher", "updated_at"])
    if previous_id and next_id:
        action = "class.teacher_reassigned"
    elif next_id:
        action = "class.teacher_assigned"
    else:
        action = "class.teacher_unassigned"
    record_model_audit_event(
        actor=actor,
        action=action,
        target=locked,
        target_snapshot={"code": locked.code, "status": locked.status},
        metadata={
            "previous_teacher_id": str(previous_id) if previous_id else None,
            "teacher_id": str(next_id) if next_id else None,
        },
    )
    return locked


@transaction.atomic
def add_students(
    *, actor: User, classroom: Classroom, students: Iterable[User]
) -> list[StudentMembership]:
    _require_admin(actor)
    locked_class = Classroom.objects.select_for_update().get(pk=classroom.pk)
    if locked_class.status != Classroom.Status.ACTIVE:
        raise ValidationError("Students can be added only to active classes.")
    student_list = list(students)
    if not student_list:
        raise ValidationError("Select at least one student.")
    locked_students = [_locked_active_student(student) for student in student_list]
    if len({student.pk for student in locked_students}) != len(locked_students):
        raise ValidationError("Each student may be selected only once.")

    memberships = []
    for student in locked_students:
        try:
            with transaction.atomic():
                membership = StudentMembership.objects.create(
                    classroom=locked_class,
                    student=student,
                    joined_at=timezone.now(),
                    added_by=actor,
                )
        except IntegrityError as error:
            raise ValidationError(
                f"{student.get_full_name() or student.username} already has an open membership."
            ) from error
        record_model_audit_event(
            actor=actor,
            action="membership.created",
            target=membership,
            target_snapshot={
                "classroom_id": str(locked_class.pk),
                "student_id": str(student.pk),
                "open": True,
            },
        )
        memberships.append(membership)
    return memberships


@transaction.atomic
def close_membership(
    *, actor: User, membership: StudentMembership, reason: str = ""
) -> StudentMembership:
    _require_admin(actor)
    locked = StudentMembership.objects.select_for_update().get(pk=membership.pk)
    if locked.left_at is not None:
        raise ValidationError("This membership is already closed.")
    locked.left_at = timezone.now()
    locked.removed_by = actor
    locked.save(update_fields=["left_at", "removed_by"])
    record_model_audit_event(
        actor=actor,
        action="membership.closed",
        target=locked,
        target_snapshot={
            "classroom_id": str(locked.classroom_id),
            "student_id": str(locked.student_id),
            "open": False,
        },
        reason=reason.strip() or None,
    )
    return locked


@transaction.atomic
def archive_classroom(*, actor: User, classroom: Classroom, reason: str) -> Classroom:
    _require_admin(actor)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValidationError("An archive reason is required.")
    locked = Classroom.objects.select_for_update().get(pk=classroom.pk)
    if locked.status != Classroom.Status.ACTIVE:
        raise ValidationError("This class is already archived.")
    locked.status = Classroom.Status.ARCHIVED
    locked.archived_at = timezone.now()
    locked.archived_by = actor
    locked.archive_reason = normalized_reason
    locked.save(
        update_fields=["status", "archived_at", "archived_by", "archive_reason", "updated_at"]
    )
    record_model_audit_event(
        actor=actor,
        action="class.archived",
        target=locked,
        target_snapshot={"code": locked.code, "status": locked.status},
        reason=normalized_reason,
    )
    return locked


@transaction.atomic
def reactivate_classroom(*, actor: User, classroom: Classroom) -> Classroom:
    _require_admin(actor)
    locked = Classroom.objects.select_for_update().get(pk=classroom.pk)
    if locked.status != Classroom.Status.ARCHIVED:
        raise ValidationError("This class is already active.")
    if locked.teacher_id:
        teacher = User.objects.select_for_update().get(pk=locked.teacher_id)
        if teacher.role != User.Role.TEACHER or not teacher.is_active:
            raise ValidationError("Unassign the inactive or invalid teacher before reactivating.")
    locked.status = Classroom.Status.ACTIVE
    locked.archived_at = None
    locked.archived_by = None
    locked.archive_reason = None
    locked.save(
        update_fields=["status", "archived_at", "archived_by", "archive_reason", "updated_at"]
    )
    record_model_audit_event(
        actor=actor,
        action="class.reactivated",
        target=locked,
        target_snapshot={"code": locked.code, "status": locked.status},
    )
    return locked


@transaction.atomic
def delete_unused_classroom(
    *, actor: User, classroom: Classroom, confirmed_code: str, reason: str
) -> None:
    _require_admin(actor)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValidationError("A deletion reason is required.")
    locked = Classroom.objects.select_for_update().get(pk=classroom.pk)
    if locked.status != Classroom.Status.ARCHIVED:
        raise ValidationError("Archive the class before requesting permanent deletion.")
    if confirmed_code.strip() != locked.code:
        raise ValidationError("Enter the exact class code to confirm deletion.")
    if locked.teacher_id is not None:
        raise ValidationError("Unassign the teacher before deleting an unused class.")
    if StudentMembership.objects.filter(classroom=locked).exists():
        raise ValidationError("Membership history protects this class from deletion.")

    target_id = locked.pk
    snapshot = {"code": locked.code, "name": locked.name, "status": locked.status}
    locked.delete()
    record_audit_event(
        actor=actor,
        action="class.deleted",
        target_type="classrooms.classroom",
        target_id=target_id,
        target_snapshot=snapshot,
        reason=normalized_reason,
    )
