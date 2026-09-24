from __future__ import annotations

from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from apps.accounts.models import User
from apps.accounts.services.lifecycle import (
    create_managed_user,
    deactivate_user,
    reactivate_user,
)
from apps.core.models import AuditEvent
from tests.factories import make_audit_event, make_user


PASSWORD = "Safe-Test-Password!2468"


class AccountLifecycleServiceTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin", password=PASSWORD)

    def test_admin_creates_teacher_or_student_atomically_and_audits(self):
        teacher = create_managed_user(
            actor=self.admin,
            role=User.Role.TEACHER,
            username="managed-teacher",
            password=PASSWORD,
            first_name=" Grace ",
            last_name=" Hopper ",
            email=" Teacher@Example.COM ",
        )
        self.assertEqual((teacher.first_name, teacher.last_name), ("Grace", "Hopper"))
        self.assertEqual(teacher.email, "Teacher@example.com")
        self.assertTrue(teacher.check_password(PASSWORD))
        event = AuditEvent.objects.get(action="user.created", target_id=teacher.pk)
        self.assertEqual(event.actor, self.admin)
        self.assertNotIn("password", event.target_snapshot_json)

    def test_ordinary_lifecycle_rejects_admin_creation_and_nonadmin_actor(self):
        with self.assertRaises(ValidationError):
            create_managed_user(
                actor=self.admin,
                role=User.Role.ADMIN,
                username="forged-admin",
                password=PASSWORD,
                first_name="Forged",
                last_name="Admin",
            )
        teacher = make_user(role="teacher")
        with self.assertRaises(PermissionDenied):
            create_managed_user(
                actor=teacher,
                role=User.Role.STUDENT,
                username="forged-student",
                password=PASSWORD,
                first_name="Forged",
                last_name="Student",
            )

    def test_deactivation_invalidates_all_sessions_and_preserves_history(self):
        target = make_user(role="student", password=PASSWORD)
        first = Client()
        second = Client()
        first.force_login(target)
        second.force_login(target)
        session_keys = {first.session.session_key, second.session.session_key}

        updated = deactivate_user(
            actor=self.admin,
            target=target,
            reason="  Account access withdrawn  ",
        )
        self.assertFalse(updated.is_active)
        self.assertEqual(updated.deactivation_reason, "Account access withdrawn")
        self.assertEqual(updated.deactivated_by, self.admin)
        self.assertFalse(Session.objects.filter(session_key__in=session_keys).exists())
        event = AuditEvent.objects.get(action="user.deactivated", target_id=target.pk)
        self.assertEqual(event.reason, "Account access withdrawn")
        self.assertEqual(event.metadata_json["invalidated_sessions"], 2)

    def test_reactivation_clears_lifecycle_fields_and_audits(self):
        target = make_user(role="teacher", password=PASSWORD)
        deactivate_user(actor=self.admin, target=target, reason="Temporary hold")
        reactivated = reactivate_user(actor=self.admin, target=target)
        self.assertTrue(reactivated.is_active)
        self.assertIsNone(reactivated.deactivated_at)
        self.assertIsNone(reactivated.deactivated_by)
        self.assertIsNone(reactivated.deactivation_reason)
        self.assertTrue(AuditEvent.objects.filter(action="user.reactivated", target_id=target.pk).exists())

    def test_deactivation_requires_reason_and_rejects_admin_target(self):
        target = make_user(role="student")
        with self.assertRaises(ValidationError):
            deactivate_user(actor=self.admin, target=target, reason="   ")
        with self.assertRaises(ValidationError):
            deactivate_user(actor=self.admin, target=self.admin, reason="Not permitted")


class AuditImmutabilityTests(TestCase):
    def test_audit_event_update_and_delete_are_rejected_by_database(self):
        event = make_audit_event()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditEvent.objects.filter(pk=event.pk).delete()

