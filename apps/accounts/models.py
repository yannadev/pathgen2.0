from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        TEACHER = "teacher", "Teacher"
        STUDENT = "student", "Student"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=16, choices=Role.choices)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="deactivated_users",
    )
    deactivation_reason = models.TextField(null=True, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["role"]

    class Meta:
        db_table = "accounts_user"
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["admin", "teacher", "student"]),
                name="acct_user_role_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        is_active=True,
                        deactivated_at__isnull=True,
                        deactivated_by__isnull=True,
                        deactivation_reason__isnull=True,
                    )
                    | (
                        Q(
                            is_active=False,
                            deactivated_at__isnull=False,
                            deactivated_by__isnull=False,
                            deactivation_reason__isnull=False,
                        )
                        & ~Q(deactivation_reason="")
                    )
                ),
                name="acct_user_deactivation_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["role", "is_active"], name="acct_user_role_active_idx"),
            models.Index(fields=["deactivated_at"], name="acct_user_deactivated_idx"),
            models.Index(fields=["anonymized_at"], name="acct_user_anonymized_idx"),
        ]
