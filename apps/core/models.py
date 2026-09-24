from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class SystemSetting(models.Model):
    singleton_key = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    study_access_enabled = models.BooleanField(default=True)
    posttest_access_enabled = models.BooleanField(default=False)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="system_setting_changes",
    )
    changed_at = models.DateTimeField()
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "core_system_setting"
        constraints = [
            models.CheckConstraint(condition=Q(singleton_key=1), name="setting_singleton_key_valid"),
            models.CheckConstraint(condition=Q(revision__gte=0), name="setting_revision_nonnegative"),
        ]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=128)
    target_type = models.CharField(max_length=128)
    target_id = models.UUIDField()
    target_snapshot_json = models.JSONField(default=dict)
    reason = models.TextField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_audit_event"
        constraints = [
            models.CheckConstraint(condition=~Q(action=""), name="audit_action_nonblank"),
            models.CheckConstraint(condition=~Q(target_type=""), name="audit_target_type_nonblank"),
        ]
        indexes = [
            models.Index(fields=["created_at"], name="audit_created_idx"),
            models.Index(fields=["action", "created_at"], name="audit_action_created_idx"),
            models.Index(fields=["actor", "created_at"], name="audit_actor_created_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_lookup_idx"),
        ]
