from __future__ import annotations

import uuid
from typing import Any

from django.db import models

from apps.core.models import AuditEvent


def record_audit_event(
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    actor: models.Model | None = None,
    target_snapshot: dict[str, Any] | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append a minimized audit event without logging request secrets."""
    normalized_action = action.strip()
    normalized_target_type = target_type.strip()
    normalized_reason = reason.strip() if reason else None
    if not normalized_action:
        raise ValueError("Audit action must be nonblank.")
    if not normalized_target_type:
        raise ValueError("Audit target type must be nonblank.")
    return AuditEvent.objects.create(
        actor=actor,
        action=normalized_action,
        target_type=normalized_target_type,
        target_id=target_id,
        target_snapshot_json=target_snapshot or {},
        reason=normalized_reason,
        metadata_json=metadata or {},
    )


def record_model_audit_event(
    *,
    action: str,
    target: models.Model,
    actor: models.Model | None = None,
    target_snapshot: dict[str, Any] | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    target_id = target.pk
    if not isinstance(target_id, uuid.UUID):
        raise TypeError("Audited model targets must have UUID primary keys.")
    return record_audit_event(
        actor=actor,
        action=action,
        target_type=target._meta.label_lower,
        target_id=target_id,
        target_snapshot=target_snapshot,
        reason=reason,
        metadata=metadata,
    )

