from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q

from apps.learning.models import Session


class SessionFeedback(models.Model):
    class GenerationStatus(models.TextChoices):
        GENERATED = "generated", "Generated"
        FALLBACK = "fallback", "Fallback"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        Session,
        on_delete=models.PROTECT,
        related_name="feedback",
    )
    feedback_text = models.TextField()
    generation_status = models.CharField(max_length=16, choices=GenerationStatus.choices)
    model_name = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feedback_session_feedback"
        constraints = [
            models.CheckConstraint(
                condition=Q(generation_status__in=["generated", "fallback"]),
                name="feedback_status_valid",
            ),
            models.CheckConstraint(condition=~Q(feedback_text=""), name="feedback_text_nonblank"),
            models.CheckConstraint(
                condition=(
                    Q(generation_status="generated", model_name="gpt-oss-120b")
                    | Q(generation_status="fallback", model_name__isnull=True)
                ),
                name="feedback_model_status_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["generation_status", "created_at"], name="feedback_status_created_idx")
        ]

