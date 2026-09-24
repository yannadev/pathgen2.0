from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models.deletion import ProtectedError
from django.db.models import Q


class Classroom(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="taught_classrooms",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="archived_classrooms",
    )
    archive_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "classrooms_classroom"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "archived"]),
                name="classroom_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="active",
                        archived_at__isnull=True,
                        archived_by__isnull=True,
                        archive_reason__isnull=True,
                    )
                    | (
                        Q(
                            status="archived",
                            archived_at__isnull=False,
                            archived_by__isnull=False,
                            archive_reason__isnull=False,
                        )
                        & ~Q(archive_reason="")
                    )
                ),
                name="classroom_archive_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["teacher", "status"], name="classroom_teacher_status_idx"),
            models.Index(fields=["status"], name="classroom_status_idx"),
        ]


class ProtectedMembershipQuerySet(models.QuerySet):
    def delete(self):
        raise ProtectedError(
            "Membership history is protected; close the membership instead.",
            set(self),
        )


class StudentMembership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.PROTECT,
        related_name="student_memberships",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="classroom_memberships",
    )
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_student_memberships",
    )
    removed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="removed_student_memberships",
    )

    class Meta:
        db_table = "classrooms_student_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "student"],
                condition=Q(left_at__isnull=True),
                name="membership_one_open",
            ),
            models.CheckConstraint(
                condition=Q(left_at__isnull=True) | Q(left_at__gte=models.F("joined_at")),
                name="membership_dates_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["classroom", "left_at"], name="membership_class_open_idx"),
            models.Index(fields=["student", "left_at"], name="membership_student_open_idx"),
        ]

    objects = ProtectedMembershipQuerySet.as_manager()

    def delete(self, using=None, keep_parents=False):
        raise ProtectedError(
            "Membership history is protected; close the membership instead.",
            {self},
        )
