from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.curriculum.models import Lesson, Question, QuestionChoice


class StudentPath(models.Model):
    class Status(models.TextChoices):
        PRETEST_REQUIRED = "pretest_required", "Pre-test required"
        LEARNING = "learning", "Learning"
        ACTIVITY_READY = "activity_ready", "Activity ready"
        POSTTEST_READY = "posttest_ready", "Post-test ready"
        COMPLETED = "completed", "Completed"

    class Stage(models.TextChoices):
        PRETEST = "pretest", "Pre-test"
        LESSON = "lesson", "Lesson"
        REGULAR = "regular", "Regular"
        ADDITIONAL = "additional", "Additional"
        FOUNDATIONAL = "foundational", "Foundational"
        ACTIVITY = "activity", "Activity"
        POSTTEST = "posttest", "Post-test"

    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        primary_key=True,
        on_delete=models.PROTECT,
        related_name="learning_path",
    )
    status = models.CharField(max_length=24, choices=Status.choices)
    current_lesson = models.ForeignKey(
        Lesson,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="current_student_paths",
    )
    current_stage = models.CharField(max_length=16, choices=Stage.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learning_student_path"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    status__in=[
                        "pretest_required",
                        "learning",
                        "activity_ready",
                        "posttest_ready",
                        "completed",
                    ]
                ),
                name="student_path_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    current_stage__in=[
                        "pretest",
                        "lesson",
                        "regular",
                        "additional",
                        "foundational",
                        "activity",
                        "posttest",
                    ]
                ),
                name="student_path_stage_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "current_stage"], name="student_path_status_stage_idx"),
            models.Index(fields=["updated_at"], name="student_path_updated_idx"),
        ]


class Session(models.Model):
    class SessionType(models.TextChoices):
        PRETEST = "pretest", "Pre-test"
        REGULAR = "regular", "Regular"
        ADDITIONAL = "additional", "Additional"
        FOUNDATIONAL = "foundational", "Foundational"
        ACTIVITY = "activity", "Activity"
        POSTTEST = "posttest", "Post-test"

    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="learning_sessions",
    )
    session_type = models.CharField(max_length=16, choices=SessionType.choices)
    lesson = models.ForeignKey(
        Lesson,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="learning_sessions",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ISSUED)
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "learning_session"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    session_type__in=[
                        "pretest",
                        "regular",
                        "additional",
                        "foundational",
                        "activity",
                        "posttest",
                    ]
                ),
                name="session_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["issued", "in_progress", "submitted", "completed"]),
                name="session_status_valid",
            ),
            models.CheckConstraint(condition=Q(attempt_number__gt=0), name="session_attempt_positive"),
            models.CheckConstraint(
                condition=(
                    Q(session_type__in=["regular", "additional", "foundational"], lesson__isnull=False)
                    | Q(session_type__in=["pretest", "activity", "posttest"], lesson__isnull=True)
                ),
                name="session_lesson_scope_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status="issued",
                        started_at__isnull=True,
                        submitted_at__isnull=True,
                        completed_at__isnull=True,
                    )
                    | Q(
                        status="in_progress",
                        started_at__isnull=False,
                        submitted_at__isnull=True,
                        completed_at__isnull=True,
                    )
                    | Q(
                        status="submitted",
                        started_at__isnull=False,
                        submitted_at__isnull=False,
                        completed_at__isnull=True,
                    )
                    | Q(
                        status="completed",
                        started_at__isnull=False,
                        submitted_at__isnull=False,
                        completed_at__isnull=False,
                    )
                ),
                name="session_status_timestamps_valid",
            ),
            models.CheckConstraint(
                condition=Q(submitted_at__isnull=True) | Q(submitted_at__gte=models.F("started_at")),
                name="session_submitted_order_valid",
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=models.F("submitted_at")),
                name="session_completed_order_valid",
            ),
            models.UniqueConstraint(
                fields=["student", "session_type", "lesson", "attempt_number"],
                condition=Q(lesson__isnull=False),
                name="session_lesson_attempt_unique",
            ),
            models.UniqueConstraint(
                fields=["student", "session_type", "attempt_number"],
                condition=Q(lesson__isnull=True),
                name="session_course_attempt_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["student", "status", "created_at"], name="sess_student_status_time_idx"),
            models.Index(fields=["student", "session_type", "lesson"], name="sess_student_type_lesson_idx"),
            models.Index(fields=["session_type", "completed_at"], name="session_type_completed_idx"),
        ]


class SessionItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(Session, on_delete=models.PROTECT, related_name="items")
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="session_items",
    )
    display_order = models.PositiveIntegerField()

    class Meta:
        db_table = "learning_session_item"
        constraints = [
            models.UniqueConstraint(fields=["session", "question"], name="session_item_question_unique"),
            models.UniqueConstraint(fields=["session", "display_order"], name="session_item_order_unique"),
            models.CheckConstraint(condition=Q(display_order__gt=0), name="session_item_order_positive"),
        ]
        indexes = [
            models.Index(fields=["session", "display_order"], name="session_item_order_idx"),
        ]


class Response(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_item = models.OneToOneField(
        SessionItem,
        on_delete=models.PROTECT,
        related_name="response",
    )
    selected_choice = models.ForeignKey(
        QuestionChoice,
        on_delete=models.PROTECT,
        related_name="responses",
    )
    hint_used = models.BooleanField(default=False)
    answered_at = models.DateTimeField()

    class Meta:
        db_table = "learning_response"
        indexes = [models.Index(fields=["answered_at"], name="response_answered_idx")]
