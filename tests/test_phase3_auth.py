from __future__ import annotations

import time

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.middleware import SESSION_SEEN_KEY, SESSION_STARTED_KEY
from apps.core.models import AuditEvent, SystemSetting
from tests.factories import make_system_setting, make_user


PASSWORD = "Safe-Test-Password!2468"
NEW_PASSWORD = "New-Safe-Password!8642"


class LoginLogoutTests(TestCase):
    def test_login_is_csrf_protected_and_rotates_session(self):
        user = make_user(role="teacher", password=PASSWORD)
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            csrf_client.post(reverse("account:login"), {"username": user.username, "password": PASSWORD}).status_code,
            403,
        )

        client = Client()
        session = client.session
        session["pre_login_marker"] = True
        session.save()
        previous_key = session.session_key
        response = client.post(
            reverse("account:login"),
            {"username": user.username, "password": PASSWORD},
        )
        self.assertRedirects(response, reverse("account:my_account"))
        self.assertNotEqual(client.session.session_key, previous_key)
        self.assertEqual(client.session[SESSION_KEY], str(user.pk))
        self.assertIn(SESSION_STARTED_KEY, client.session)

    def test_invalid_and_inactive_accounts_receive_same_generic_error(self):
        active = make_user(role="teacher", password=PASSWORD)
        inactive = make_user(role="teacher", password=PASSWORD)
        admin = make_user(role="admin", password=PASSWORD)
        from apps.accounts.services.lifecycle import deactivate_user

        deactivate_user(actor=admin, target=inactive, reason="Synthetic security test")

        unknown_response = self.client.post(
            reverse("account:login"),
            {"username": "does-not-exist", "password": PASSWORD},
        )
        active_response = self.client.post(
            reverse("account:login"),
            {"username": active.username, "password": "wrong-password"},
        )
        inactive_response = self.client.post(
            reverse("account:login"),
            {"username": inactive.username, "password": PASSWORD},
        )
        generic = b"Unable to sign in with those credentials."
        self.assertContains(unknown_response, generic.decode())
        self.assertContains(active_response, generic.decode())
        self.assertContains(inactive_response, generic.decode())
        self.assertNotContains(inactive_response, "inactive")
        self.assertNotContains(unknown_response, "does-not-exist")

    def test_study_access_blocks_only_students_and_class_is_not_required(self):
        admin = make_user(role="admin", password=PASSWORD)
        student = make_user(role="student", password=PASSWORD)
        teacher = make_user(role="teacher", password=PASSWORD)
        make_system_setting(changed_by=admin, study_access_enabled=False)

        student_response = self.client.post(
            reverse("account:login"),
            {"username": student.username, "password": PASSWORD},
        )
        self.assertEqual(student_response.status_code, 403)
        self.assertContains(student_response, "Student Study Access is currently closed", status_code=403)
        self.assertNotIn(SESSION_KEY, self.client.session)

        teacher_response = self.client.post(
            reverse("account:login"),
            {"username": teacher.username, "password": PASSWORD},
        )
        self.assertRedirects(teacher_response, reverse("account:my_account"))

        self.client.logout()
        SystemSetting.objects.filter(singleton_key=1).update(study_access_enabled=True)
        student_response = self.client.post(
            reverse("account:login"),
            {"username": student.username, "password": PASSWORD},
        )
        self.assertRedirects(student_response, reverse("account:my_account"))

    def test_next_redirect_must_be_same_site_and_account_scoped(self):
        user = make_user(role="teacher", password=PASSWORD)
        external = self.client.post(
            reverse("account:login"),
            {"username": user.username, "password": PASSWORD, "next": "https://example.com/steal"},
        )
        self.assertRedirects(external, reverse("account:my_account"))

        self.client.logout()
        unrelated = self.client.post(
            reverse("account:login"),
            {"username": user.username, "password": PASSWORD, "next": "/health/"},
        )
        self.assertRedirects(unrelated, reverse("account:my_account"))

        self.client.logout()
        allowed_path = reverse("account:update_name")
        allowed = self.client.post(
            reverse("account:login"),
            {"username": user.username, "password": PASSWORD, "next": allowed_path},
        )
        self.assertRedirects(allowed, allowed_path)

    def test_logout_get_only_confirms_and_post_clears_session(self):
        user = make_user(role="teacher", password=PASSWORD)
        self.client.force_login(user)
        get_response = self.client.get(reverse("account:logout"))
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_KEY], str(user.pk))

        post_response = self.client.post(reverse("account:logout"))
        self.assertRedirects(post_response, reverse("account:login"))
        self.assertNotIn(SESSION_KEY, self.client.session)
        self.assertTrue(AuditEvent.objects.filter(action="auth.logout", target_id=user.pk).exists())

    def test_logout_post_requires_csrf(self):
        user = make_user(role="teacher", password=PASSWORD)
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.post(reverse("account:logout")).status_code, 403)
        self.assertEqual(client.session[SESSION_KEY], str(user.pk))

    def test_idle_session_expires_and_clears_authentication(self):
        user = make_user(role="teacher", password=PASSWORD)
        self.client.force_login(user)
        session = self.client.session
        expired = int(time.time()) - 60 * 60
        session[SESSION_STARTED_KEY] = expired
        session[SESSION_SEEN_KEY] = expired
        session.save()
        response = self.client.get(reverse("account:my_account"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("account:login")))
        self.assertNotIn(SESSION_KEY, self.client.session)


class OwnAccountChangeTests(TestCase):
    def test_name_change_is_trimmed_and_cannot_change_username_or_role(self):
        user = make_user(role="student", username="fixed-user", password=PASSWORD)
        self.client.force_login(user)
        response = self.client.post(
            reverse("account:update_name"),
            {
                "first_name": "  Ada  ",
                "last_name": "  Lovelace ",
                "username": "forged",
                "role": "admin",
            },
        )
        self.assertRedirects(response, reverse("account:my_account"))
        user.refresh_from_db()
        self.assertEqual((user.first_name, user.last_name), ("Ada", "Lovelace"))
        self.assertEqual(user.username, "fixed-user")
        self.assertEqual(user.role, "student")
        self.assertTrue(AuditEvent.objects.filter(action="user.name_updated", target_id=user.pk).exists())

    def test_password_change_preserves_current_session_and_invalidates_others(self):
        user = make_user(role="teacher", password=PASSWORD)
        current = Client()
        other = Client()
        current.force_login(user)
        other.force_login(user)
        other_key = other.session.session_key

        response = current.post(
            reverse("account:update_password"),
            {
                "old_password": PASSWORD,
                "new_password1": NEW_PASSWORD,
                "new_password2": NEW_PASSWORD,
            },
        )
        self.assertRedirects(response, reverse("account:my_account"))
        self.assertEqual(current.session[SESSION_KEY], str(user.pk))
        self.assertFalse(Session.objects.filter(session_key=other_key).exists())
        user.refresh_from_db()
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertTrue(AuditEvent.objects.filter(action="user.password_changed", target_id=user.pk).exists())
