from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.accounts.throttling import LOGIN_HARD_LIMIT, SENSITIVE_LIMIT
from tests.factories import make_user


PASSWORD = "Safe-Test-Password!2468"


class RateThrottleTests(TestCase):
    def test_login_throttle_is_bounded_and_generic(self):
        user = make_user(role="teacher", password=PASSWORD)
        with patch("apps.accounts.throttling.LOGIN_PROGRESSIVE_AFTER", 99):
            for _ in range(LOGIN_HARD_LIMIT):
                response = self.client.post(
                    reverse("account:login"),
                    {"username": user.username, "password": "wrong"},
                    REMOTE_ADDR="203.0.113.10",
                )
                self.assertEqual(response.status_code, 200)
            blocked = self.client.post(
                reverse("account:login"),
                {"username": user.username, "password": "wrong"},
                REMOTE_ADDR="203.0.113.10",
            )
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Unable to complete that request right now", status_code=429)
        self.assertIn("Retry-After", blocked)

    def test_password_change_attempts_are_throttled(self):
        user = make_user(role="teacher", password=PASSWORD)
        self.client.force_login(user)
        for _ in range(SENSITIVE_LIMIT):
            response = self.client.post(
                reverse("account:update_password"),
                {
                    "old_password": "wrong",
                    "new_password1": "Another-Safe-Password!2468",
                    "new_password2": "Another-Safe-Password!2468",
                },
                REMOTE_ADDR="203.0.113.11",
            )
            self.assertEqual(response.status_code, 200)
        blocked = self.client.post(
            reverse("account:update_password"),
            {
                "old_password": "wrong",
                "new_password1": "Another-Safe-Password!2468",
                "new_password2": "Another-Safe-Password!2468",
            },
            REMOTE_ADDR="203.0.113.11",
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertContains(blocked, "Unable to complete that request right now", status_code=429)
