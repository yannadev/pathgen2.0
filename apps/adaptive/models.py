from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.curriculum.models import Skill
from apps.learning.models import Response, Session


class SkillMastery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="skill_masteries",
    )
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="student_masteries")
    p_known = models.DecimalField(max_digits=5, decimal_places=4)
    evidence_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "adaptive_skill_mastery"
        constraints = [
            models.UniqueConstraint(fields=["student", "skill"], name="mastery_student_skill_unique"),
            models.CheckConstraint(condition=Q(p_known__gte=0, p_known__lte=1), name="mastery_p_known_valid"),
            models.CheckConstraint(condition=Q(evidence_count__gte=0), name="mastery_evidence_nonnegative"),
        ]
        indexes = [models.Index(fields=["student", "skill"], name="mastery_student_skill_idx")]


class MasteryEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mastery = models.ForeignKey(
        SkillMastery,
        on_delete=models.PROTECT,
        related_name="events",
    )
    response = models.OneToOneField(
        Response,
        on_delete=models.PROTECT,
        related_name="mastery_event",
    )
    p_before = models.DecimalField(max_digits=5, decimal_places=4)
    p_after_observation = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    p_after_learning = models.DecimalField(max_digits=5, decimal_places=4)
    learning_transition_applied = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "adaptive_mastery_event"
        constraints = [
            models.CheckConstraint(condition=Q(p_before__gte=0, p_before__lte=1), name="event_p_before_valid"),
            models.CheckConstraint(
                condition=Q(p_after_observation__isnull=True)
                | Q(p_after_observation__gte=0, p_after_observation__lte=1),
                name="event_p_observation_valid",
            ),
            models.CheckConstraint(
                condition=Q(p_after_learning__gte=0, p_after_learning__lte=1),
                name="event_p_learning_valid",
            ),
        ]
        indexes = [models.Index(fields=["mastery", "created_at"], name="event_mastery_created_idx")]


class Decision(models.Model):
    class Action(models.TextChoices):
        ADDITIONAL_EXERCISE = "additional_exercise", "Additional exercise"
        FOUNDATIONAL_EXERCISE = "foundational_exercise", "Foundational exercise"
        PROGRESS = "progress", "Progress"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        Session,
        on_delete=models.PROTECT,
        related_name="decision",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    reason_code = models.CharField(max_length=64)
    input_snapshot_json = models.JSONField(default=dict)
    support_cutoff = models.DecimalField(max_digits=5, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "adaptive_decision"
        constraints = [
            models.CheckConstraint(
                condition=Q(action__in=["additional_exercise", "foundational_exercise", "progress"]),
                name="decision_action_valid",
            ),
            models.CheckConstraint(condition=~Q(reason_code=""), name="decision_reason_nonblank"),
            models.CheckConstraint(
                condition=Q(support_cutoff__gte=0, support_cutoff__lte=1),
                name="decision_cutoff_valid",
            ),
        ]
        indexes = [models.Index(fields=["action", "created_at"], name="decision_action_created_idx")]


class DecisionTargetSkill(models.Model):
    class TargetKind(models.TextChoices):
        NEXT_EXERCISE = "next_exercise", "Next exercise"
        FOLLOW_UP = "follow_up", "Follow-up"

    pk = models.CompositePrimaryKey("decision", "skill", "target_kind")
    decision = models.ForeignKey(
        Decision,
        on_delete=models.PROTECT,
        related_name="target_skills",
    )
    skill = models.ForeignKey(
        Skill,
        on_delete=models.PROTECT,
        related_name="decision_targets",
    )
    target_kind = models.CharField(max_length=16, choices=TargetKind.choices)

    class Meta:
        db_table = "adaptive_decision_target_skill"
        constraints = [
            models.CheckConstraint(
                condition=Q(target_kind__in=["next_exercise", "follow_up"]),
                name="decision_target_kind_valid",
            ),
            models.UniqueConstraint(
                fields=["decision", "skill", "target_kind"],
                name="decision_target_unique",
            ),
        ]
        indexes = [models.Index(fields=["target_kind", "skill"], name="decision_target_kind_skill_idx")]

