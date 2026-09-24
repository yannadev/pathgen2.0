from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.core.models import AuditEvent


class TrustedAdminBootstrapTests(TestCase):
    def test_bootstrap_creates_framework_and_pathgen_admin_without_echoing_password(self):
        output = StringIO()
        password = "Bootstrap-Password!2468"
        with patch.dict("os.environ", {"TEST_BOOTSTRAP_PASSWORD": password}):
            call_command(
                "bootstrap_admin",
                username="trusted-admin",
                first_name="Trusted",
                last_name="Administrator",
                email="admin@example.com",
                password_env="TEST_BOOTSTRAP_PASSWORD",
                stdout=output,
            )
        admin = User.objects.get(username="trusted-admin")
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password(password))
        self.assertNotIn(password, output.getvalue())
        self.assertTrue(
            AuditEvent.objects.filter(action="user.admin_bootstrapped", target_id=admin.pk).exists()
        )

    def test_bootstrap_requires_environment_password_and_unique_username(self):
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(CommandError):
            call_command(
                "bootstrap_admin",
                username="missing-password",
                first_name="Missing",
                last_name="Password",
                password_env="ABSENT_BOOTSTRAP_PASSWORD",
            )
        User.objects.create_user(username="already-used", role="teacher")
        with patch.dict("os.environ", {"TEST_BOOTSTRAP_PASSWORD": "Bootstrap-Password!2468"}):
            with self.assertRaises(CommandError):
                call_command(
                    "bootstrap_admin",
                    username="already-used",
                    first_name="Duplicate",
                    last_name="Account",
                    password_env="TEST_BOOTSTRAP_PASSWORD",
                )

