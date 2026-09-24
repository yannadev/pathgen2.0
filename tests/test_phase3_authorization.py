from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.permissions import (
    admin_required,
    has_role,
    is_admin,
    is_student,
    is_teacher,
)
from apps.accounts.selectors import users_visible_to
from apps.classrooms.models import Classroom, StudentMembership
from apps.classrooms.selectors import classrooms_visible_to
from tests.factories import make_classroom, make_membership, make_user


class RolePermissionTests(TestCase):
    def test_role_helpers_require_active_authenticated_user(self):
        admin = make_user(role="admin")
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        self.assertTrue(is_admin(admin))
        self.assertTrue(is_teacher(teacher))
        self.assertTrue(is_student(student))
        self.assertFalse(has_role(student, "admin"))
        student.is_active = False
        self.assertFalse(is_student(student))

    def test_role_decorator_redirects_anonymous_and_denies_wrong_role(self):
        @admin_required
        def protected(request):
            return HttpResponse("ok")

        request = RequestFactory().get("/protected/")
        request.user = AnonymousUser()
        self.assertEqual(protected(request).status_code, 302)

        request.user = make_user(role="teacher")
        with self.assertRaises(PermissionDenied):
            protected(request)

        request.user = make_user(role="admin")
        self.assertEqual(protected(request).status_code, 200)


class AuthorizedSelectorTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin")
        self.teacher = make_user(role="teacher")
        self.other_teacher = make_user(role="teacher")
        self.student = make_user(role="student")
        self.other_student = make_user(role="student")
        self.classroom = make_classroom(teacher=self.teacher)
        self.other_classroom = make_classroom(teacher=self.other_teacher)
        make_membership(
            classroom=self.classroom,
            student=self.student,
            added_by=self.admin,
        )
        make_membership(
            classroom=self.other_classroom,
            student=self.other_student,
            added_by=self.admin,
        )

    def test_admin_teacher_and_student_user_scopes(self):
        admin_ids = set(users_visible_to(self.admin).values_list("id", flat=True))
        self.assertIn(self.teacher.id, admin_ids)
        self.assertIn(self.student.id, admin_ids)
        self.assertNotIn(self.admin.id, admin_ids)

        teacher_ids = set(users_visible_to(self.teacher).values_list("id", flat=True))
        self.assertEqual(teacher_ids, {self.student.id})

        student_ids = set(users_visible_to(self.student).values_list("id", flat=True))
        self.assertEqual(student_ids, {self.student.id})

    def test_closed_membership_and_reassignment_remove_teacher_scope(self):
        membership = StudentMembership.objects.get(student=self.student)
        from django.utils import timezone

        membership.left_at = timezone.now()
        membership.removed_by = self.admin
        membership.save(update_fields=["left_at", "removed_by"])
        self.assertFalse(users_visible_to(self.teacher).filter(pk=self.student.pk).exists())

        self.classroom.teacher = self.other_teacher
        self.classroom.save(update_fields=["teacher"])
        self.assertFalse(classrooms_visible_to(self.teacher).filter(pk=self.classroom.pk).exists())

    def test_classroom_querysets_are_object_scoped(self):
        self.assertEqual(
            set(classrooms_visible_to(self.teacher).values_list("id", flat=True)),
            {self.classroom.id},
        )
        self.assertEqual(
            set(classrooms_visible_to(self.student).values_list("id", flat=True)),
            {self.classroom.id},
        )
        self.assertEqual(classrooms_visible_to(AnonymousUser()).count(), 0)

