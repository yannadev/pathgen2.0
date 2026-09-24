from __future__ import annotations

import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import is_admin
from apps.core.models import SystemSetting
from apps.core.services.audit import record_audit_event


SYSTEM_SETTING_TARGET_ID = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://pathgen.local/core/system-setting/1",
)


class SettingsRevisionConflict(Exception):
    """Raised when an administrator submits a stale settings revision."""

    def __init__(self, current: SystemSetting):
        self.current = current
        super().__init__("The access settings changed while you were reviewing them.")


def _require_admin(actor: User) -> None:
    if not is_admin(actor):
        raise PermissionDenied


@transaction.atomic
def initialize_system_setting(*, actor: User) -> SystemSetting:
    """Create the documented singleton with safe defaults during trusted setup."""
    _require_admin(actor)
    setting = SystemSetting.objects.select_for_update().filter(singleton_key=1).first()
    if setting is not None:
        return setting
    setting = SystemSetting.objects.create(
        singleton_key=1,
        study_access_enabled=True,
        posttest_access_enabled=False,
        changed_by=actor,
        changed_at=timezone.now(),
        revision=0,
    )
    record_audit_event(
        actor=actor,
        action="settings.initialized",
        target_type="core.systemsetting",
        target_id=SYSTEM_SETTING_TARGET_ID,
        target_snapshot={
            "study_access_enabled": True,
            "posttest_access_enabled": False,
            "revision": 0,
        },
    )
    return setting


@transaction.atomic
def update_global_override(
    *,
    actor: User,
    field: str,
    enabled: bool,
    expected_revision: int,
    reason: str,
) -> SystemSetting:
    _require_admin(actor)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValidationError({"reason": "Explain why this access setting is changing."})
    if field not in {"study_access_enabled", "posttest_access_enabled"}:
        raise ValidationError("Unknown access setting.")

    setting = SystemSetting.objects.select_for_update().get(singleton_key=1)
    if setting.revision != expected_revision:
        raise SettingsRevisionConflict(setting)

    previous = getattr(setting, field)
    if previous == enabled:
        raise ValidationError("That access setting already has the requested value.")

    setting.revision += 1
    setattr(setting, field, enabled)
    setting.changed_by = actor
    setting.changed_at = timezone.now()
    setting.save(update_fields=[field, "revision", "changed_by", "changed_at"])

    if field == "study_access_enabled":
        action = "settings.study_access_opened" if enabled else "settings.study_access_closed"
    else:
        action = "settings.posttest_unlocked" if enabled else "settings.posttest_locked"
    record_audit_event(
        actor=actor,
        action=action,
        target_type="core.systemsetting",
        target_id=SYSTEM_SETTING_TARGET_ID,
        target_snapshot={
            "study_access_enabled": setting.study_access_enabled,
            "posttest_access_enabled": setting.posttest_access_enabled,
            "revision": setting.revision,
        },
        reason=normalized_reason,
        metadata={
            "changed_field": field,
            "previous": previous,
            "current": enabled,
            "submitted_revision": expected_revision,
        },
    )
    return setting
