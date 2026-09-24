from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.core.services.settings import (
    SettingsRevisionConflict,
    initialize_system_setting,
    update_global_override,
)
from tests.factories import make_system_setting, make_user


class SystemSettingServiceTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin")
        self.setting = make_system_setting(changed_by=self.admin)

    def test_revision_checked_override_updates_and_audits_atomically(self):
        updated = update_global_override(
            actor=self.admin,
            field="study_access_enabled",
            enabled=False,
            expected_revision=0,
            reason="Pause the study window for scheduled maintenance.",
        )
        self.assertFalse(updated.study_access_enabled)
        self.assertEqual(updated.revision, 1)
        event = AuditEvent.objects.get(action="settings.study_access_closed")
        self.assertEqual(event.reason, "Pause the study window for scheduled maintenance.")
        self.assertEqual(event.metadata_json["changed_field"], "study_access_enabled")

    def test_stale_revision_changes_nothing_and_creates_no_override_audit(self):
        update_global_override(
            actor=self.admin,
            field="posttest_access_enabled",
            enabled=True,
            expected_revision=0,
            reason="Approved post-test window.",
        )
        with self.assertRaises(SettingsRevisionConflict) as caught:
            update_global_override(
                actor=self.admin,
                field="study_access_enabled",
                enabled=False,
                expected_revision=0,
                reason="A stale decision.",
            )
        self.assertEqual(caught.exception.current.revision, 1)
        self.setting.refresh_from_db()
        self.assertTrue(self.setting.study_access_enabled)
        self.assertEqual(
            AuditEvent.objects.filter(action="settings.study_access_closed").count(),
            0,
        )

    def test_override_requires_admin_reason_and_known_field(self):
        teacher = make_user(role="teacher")
        with self.assertRaises(PermissionDenied):
            update_global_override(
                actor=teacher,
                field="study_access_enabled",
                enabled=False,
                expected_revision=0,
                reason="Not authorized.",
            )
        with self.assertRaises(ValidationError):
            update_global_override(
                actor=self.admin,
                field="study_access_enabled",
                enabled=False,
                expected_revision=0,
                reason="   ",
            )
        with self.assertRaises(ValidationError):
            update_global_override(
                actor=self.admin,
                field="unknown",
                enabled=False,
                expected_revision=0,
                reason="Invalid field.",
            )

    def test_initialization_is_singleton_and_idempotent(self):
        self.setting.delete()
        initialized = initialize_system_setting(actor=self.admin)
        repeated = initialize_system_setting(actor=self.admin)
        self.assertEqual(initialized.pk, 1)
        self.assertEqual(repeated.pk, 1)
        self.assertEqual(AuditEvent.objects.filter(action="settings.initialized").count(), 1)


class OverrideViewTests(TestCase):
    def setUp(self):
        self.admin = make_user(role="admin")
        self.setting = make_system_setting(changed_by=self.admin)
        self.client.force_login(self.admin)

    def test_override_page_is_admin_only_and_success_uses_prg(self):
        response = self.client.get(reverse("admin_portal:overrides"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Global access overrides")
        self.client.logout()
        teacher = make_user(role="teacher")
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("admin_portal:overrides")).status_code, 403)

    def test_stale_revision_returns_409_with_current_state(self):
        update_global_override(
            actor=self.admin,
            field="posttest_access_enabled",
            enabled=True,
            expected_revision=0,
            reason="Open the approved post-test window.",
        )
        response = self.client.post(
            reverse("admin_portal:overrides"),
            {
                "action": "close_study",
                "revision": 0,
                "reason": "This submission reviewed an older state.",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Another administrator changed access settings", status_code=409)
        self.setting.refresh_from_db()
        self.assertTrue(self.setting.study_access_enabled)

    def test_override_post_requires_csrf(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(
            reverse("admin_portal:overrides"),
            {"action": "close_study", "revision": 0, "reason": "No token."},
        )
        self.assertEqual(response.status_code, 403)
