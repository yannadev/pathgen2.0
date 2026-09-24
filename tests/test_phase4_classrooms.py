from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.classrooms.models import Classroom, StudentMembership
from apps.classrooms.services.lifecycle import (
    add_students,
    archive_classroom,
    assign_teacher,
    close_membership,
    create_classroom,
    delete_unused_classroom,
    reactivate_classroom,
    update_classroom,
)
from apps.core.models import AuditEvent
from tests.factories import make_classroom, make_membership, make_user


class ClassroomLifecycleServiceTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin")
        self.teacher = make_user(role="teacher")
        self.student = make_user(role="student")

    def test_create_update_and_teacher_assignment_validate_roles_and_audit(self):
        classroom = create_classroom(
            actor=self.admin,
            code="G7-A",
            name="Grade 7 A",
            teacher=self.teacher,
        )
        updated = update_classroom(
            actor=self.admin,
            classroom=classroom,
            code="G7-A",
            name="Grade 7 Archimedes",
        )
        self.assertEqual(updated.name, "Grade 7 Archimedes")
        assign_teacher(actor=self.admin, classroom=classroom, teacher=None)
        self.assertTrue(AuditEvent.objects.filter(action="class.created", target_id=classroom.pk).exists())
        self.assertTrue(
            AuditEvent.objects.filter(action="class.teacher_unassigned", target_id=classroom.pk).exists()
        )
        with self.assertRaises(ValidationError):
            assign_teacher(actor=self.admin, classroom=classroom, teacher=self.student)

    def test_membership_is_opened_closed_and_never_deleted(self):
        classroom = make_classroom()
        membership = add_students(
            actor=self.admin,
            classroom=classroom,
            students=[self.student],
        )[0]
        with self.assertRaises(ValidationError):
            add_students(actor=self.admin, classroom=classroom, students=[self.student])
        closed = close_membership(
            actor=self.admin,
            membership=membership,
            reason="Moved out of the monitoring group.",
        )
        self.assertIsNotNone(closed.left_at)
        with self.assertRaises(ProtectedError):
            closed.delete()
        with self.assertRaises(ProtectedError):
            StudentMembership.objects.filter(pk=closed.pk).delete()
        self.assertTrue(AuditEvent.objects.filter(action="membership.closed", target_id=closed.pk).exists())

    def test_archive_reactivate_and_protected_delete(self):
        classroom = make_classroom()
        membership = make_membership(
            classroom=classroom,
            student=self.student,
            added_by=self.admin,
        )
        archived = archive_classroom(
            actor=self.admin,
            classroom=classroom,
            reason="Class monitoring period ended.",
        )
        with self.assertRaises(ValidationError):
            delete_unused_classroom(
                actor=self.admin,
                classroom=archived,
                confirmed_code=archived.code,
                reason="Created in error.",
            )
        self.assertTrue(StudentMembership.objects.filter(pk=membership.pk).exists())
        active = reactivate_classroom(actor=self.admin, classroom=archived)
        self.assertEqual(active.status, Classroom.Status.ACTIVE)

    def test_exceptional_delete_allows_only_archived_unassigned_unused_class(self):
        classroom = make_classroom()
        with self.assertRaises(ValidationError):
            delete_unused_classroom(
                actor=self.admin,
                classroom=classroom,
                confirmed_code=classroom.code,
                reason="Created in error.",
            )
        archived = archive_classroom(
            actor=self.admin,
            classroom=classroom,
            reason="Created in error.",
        )
        classroom_id = archived.pk
        delete_unused_classroom(
            actor=self.admin,
            classroom=archived,
            confirmed_code=archived.code,
            reason="Created in error.",
        )
        self.assertFalse(Classroom.objects.filter(pk=classroom_id).exists())
        self.assertTrue(AuditEvent.objects.filter(action="class.deleted", target_id=classroom_id).exists())

    def test_non_admin_cannot_mutate_class_structure(self):
        with self.assertRaises(PermissionDenied):
            create_classroom(actor=self.teacher, code="NOPE", name="Unauthorized")
