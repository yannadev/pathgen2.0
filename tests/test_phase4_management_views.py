from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services.lifecycle import deactivate_user, delete_unused_user
from apps.classrooms.models import Classroom, StudentMembership
from apps.core.models import AuditEvent
from tests.factories import make_classroom, make_membership, make_system_setting, make_user


PASSWORD = "Safe-Admin-Password!2468"


class AdminManagementViewTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin", password=PASSWORD)
        make_system_setting(changed_by=self.admin)
        self.client.force_login(self.admin)

    def test_admin_shell_pages_render_and_wrong_role_is_denied(self):
        for route in [
            "admin_portal:dashboard",
            "admin_portal:users",
            "admin_portal:classes",
            "admin_portal:audit_logs",
        ]:
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200, route)
            self.assertContains(response, 'meta name="color-scheme" content="only light"')

        self.client.logout()
        teacher = make_user(role="teacher")
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("admin_portal:users")).status_code, 403)

    def test_create_update_deactivate_and_reactivate_user_through_modals(self):
        create_response = self.client.post(
            reverse("admin_portal:user_create"),
            {
                "create-role": "student",
                "create-username": "managed-student",
                "create-first_name": "Managed",
                "create-last_name": "Student",
                "create-email": "",
                "create-password": "Quartz!River9Telescope",
                "create-password_confirm": "Quartz!River9Telescope",
            },
        )
        user = User.objects.get(username="managed-student")
        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(user.role, User.Role.STUDENT)

        update_response = self.client.post(
            reverse("admin_portal:user_action", args=[user.pk, "update"]),
            {
                "update-first_name": "Updated",
                "update-last_name": "Student",
                "update-email": "",
            },
        )
        self.assertEqual(update_response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Updated")

        deactivate_response = self.client.post(
            reverse("admin_portal:user_action", args=[user.pk, "deactivate"]),
            {"deactivate-reason": "Account paused by the administrator."},
        )
        self.assertEqual(deactivate_response.status_code, 302)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        reactivate_response = self.client.post(
            reverse("admin_portal:user_action", args=[user.pk, "reactivate"]),
            {},
        )
        self.assertEqual(reactivate_response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_user_create_rejects_forged_admin_role_and_post_requires_csrf(self):
        response = self.client.post(
            reverse("admin_portal:user_create"),
            {
                "create-role": "admin",
                "create-username": "forged-admin",
                "create-first_name": "Forged",
                "create-last_name": "Admin",
                "create-password": "Forged-Admin!2468",
                "create-password_confirm": "Forged-Admin!2468",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="forged-admin").exists())

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse("admin_portal:user_create"), {}).status_code, 403)

    def test_class_and_membership_actions_use_service_lifecycle(self):
        teacher = make_user(role="teacher")
        student = make_user(role="student")
        create_response = self.client.post(
            reverse("admin_portal:class_create"),
            {
                "create-code": "G7-TEST",
                "create-name": "Grade 7 Test",
                "create-teacher": str(teacher.pk),
            },
        )
        classroom = Classroom.objects.get(code="G7-TEST")
        self.assertEqual(create_response.status_code, 302)
        self.assertEqual(classroom.teacher, teacher)

        add_response = self.client.post(
            reverse("admin_portal:class_action", args=[classroom.pk, "add_students"]),
            {"add_students-students": [str(student.pk)]},
        )
        self.assertEqual(add_response.status_code, 302)
        membership = StudentMembership.objects.get(classroom=classroom, student=student)

        remove_response = self.client.post(
            reverse(
                "admin_portal:membership_remove",
                args=[classroom.pk, membership.pk],
            ),
            {"remove_student-reason": "Roster correction."},
        )
        self.assertEqual(remove_response.status_code, 302)
        membership.refresh_from_db()
        self.assertIsNotNone(membership.left_at)
        self.assertTrue(AuditEvent.objects.filter(action="membership.closed", target_id=membership.pk).exists())

    def test_user_deletion_is_exceptional_and_rejects_membership_history(self):
        unused = make_user(role="student", username="unused-student")
        deactivate_user(actor=self.admin, target=unused, reason="Created in error.")
        unused_id = unused.pk
        delete_unused_user(
            actor=self.admin,
            target=unused,
            confirmed_username="unused-student",
            reason="Created in error.",
        )
        self.assertFalse(User.objects.filter(pk=unused_id).exists())
        self.assertTrue(AuditEvent.objects.filter(action="user.deleted", target_id=unused_id).exists())

        protected = make_user(role="student", username="protected-student")
        classroom = make_classroom()
        make_membership(classroom=classroom, student=protected, added_by=self.admin)
        deactivate_user(actor=self.admin, target=protected, reason="No longer active.")
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            delete_unused_user(
                actor=self.admin,
                target=protected,
                confirmed_username="protected-student",
                reason="Privacy request.",
            )


class TeacherShellViewTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin")
        self.teacher = make_user(role="teacher")
        self.other_teacher = make_user(role="teacher")
        self.student = make_user(role="student")
        self.classroom = make_classroom(teacher=self.teacher)
        self.other_classroom = make_classroom(teacher=self.other_teacher)
        make_membership(classroom=self.classroom, student=self.student, added_by=self.admin)
        self.client.force_login(self.teacher)

    def test_teacher_sees_only_current_assigned_classes_and_roster(self):
        response = self.client.get(reverse("teacher:my_classes"))
        self.assertContains(response, self.classroom.code)
        self.assertNotContains(response, self.other_classroom.code)
        detail = self.client.get(reverse("teacher:class_detail", args=[self.classroom.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, self.student.username)
        self.assertContains(detail, "does not determine any student’s learning access")

    def test_teacher_cannot_guess_another_teachers_class(self):
        response = self.client.get(
            reverse("teacher:class_detail", args=[self.other_classroom.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_student_cannot_open_teacher_shell(self):
        self.client.logout()
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("teacher:my_classes")).status_code, 403)
