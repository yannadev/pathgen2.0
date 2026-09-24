from __future__ import annotations

from django.db.models import QuerySet

from apps.core.models import AuditEvent
from apps.core.services.settings import SYSTEM_SETTING_TARGET_ID


def setting_audit_history() -> QuerySet[AuditEvent]:
    return AuditEvent.objects.filter(
        target_type="core.systemsetting",
        target_id=SYSTEM_SETTING_TARGET_ID,
    ).select_related("actor").order_by("-created_at")


def recent_audit_events() -> QuerySet[AuditEvent]:
    return AuditEvent.objects.select_related("actor").order_by("-created_at")
