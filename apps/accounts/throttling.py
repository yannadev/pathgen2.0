from __future__ import annotations

import hashlib
import hmac
import math
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import AuditEvent
from apps.core.services.audit import record_audit_event


LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_HARD_LIMIT = 5
LOGIN_PROGRESSIVE_AFTER = 2
SENSITIVE_WINDOW_SECONDS = 15 * 60
SENSITIVE_LIMIT = 5


@dataclass(frozen=True)
class ThrottleDecision:
    allowed: bool
    retry_after: int = 0


def _request_source(request: HttpRequest) -> str:
    return request.META.get("REMOTE_ADDR", "unknown")


def _privacy_key(*parts: object) -> uuid.UUID:
    value = "\x1f".join(str(part).strip().casefold() for part in parts)
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return uuid.UUID(bytes=digest[:16])


def login_throttle_key(request: HttpRequest, username: str) -> uuid.UUID:
    return _privacy_key("login", username, _request_source(request))


def check_login_throttle(request: HttpRequest, username: str) -> ThrottleDecision:
    now = timezone.now()
    window_start = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
    target_id = login_throttle_key(request, username)
    events = AuditEvent.objects.filter(
        target_type="security.login",
        target_id=target_id,
        created_at__gte=window_start,
    )
    latest_success = (
        events.filter(action="auth.login_succeeded")
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    failures = events.filter(action="auth.login_failed")
    if latest_success:
        failures = failures.filter(created_at__gt=latest_success)
    failure_times = list(failures.order_by("created_at").values_list("created_at", flat=True))
    failure_count = len(failure_times)
    if failure_count >= LOGIN_HARD_LIMIT:
        retry_at = failure_times[0] + timedelta(seconds=LOGIN_WINDOW_SECONDS)
        return ThrottleDecision(False, max(1, math.ceil((retry_at - now).total_seconds())))
    if failure_count >= LOGIN_PROGRESSIVE_AFTER:
        delay_seconds = min(2 ** (failure_count - LOGIN_PROGRESSIVE_AFTER), 60)
        retry_at = failure_times[-1] + timedelta(seconds=delay_seconds)
        if retry_at > now:
            return ThrottleDecision(False, max(1, math.ceil((retry_at - now).total_seconds())))
    return ThrottleDecision(True)


def record_login_throttle_event(
    request: HttpRequest,
    username: str,
    *,
    succeeded: bool,
    actor: User | None = None,
) -> AuditEvent:
    return record_audit_event(
        actor=actor,
        action="auth.login_succeeded" if succeeded else "auth.login_failed",
        target_type="security.login",
        target_id=login_throttle_key(request, username),
    )


def _sensitive_key(request: HttpRequest, user: User, action: str) -> uuid.UUID:
    return _privacy_key("sensitive", user.pk, action, _request_source(request))


def check_sensitive_throttle(
    request: HttpRequest,
    *,
    user: User,
    action: str,
) -> ThrottleDecision:
    now = timezone.now()
    target_id = _sensitive_key(request, user, action)
    attempts = AuditEvent.objects.filter(
        action="security.sensitive_attempt",
        target_type="security.sensitive",
        target_id=target_id,
        created_at__gte=now - timedelta(seconds=SENSITIVE_WINDOW_SECONDS),
    ).count()
    if attempts >= SENSITIVE_LIMIT:
        return ThrottleDecision(False, SENSITIVE_WINDOW_SECONDS)
    return ThrottleDecision(True)


def record_sensitive_attempt(
    request: HttpRequest,
    *,
    user: User,
    action: str,
) -> AuditEvent:
    return record_audit_event(
        actor=user,
        action="security.sensitive_attempt",
        target_type="security.sensitive",
        target_id=_sensitive_key(request, user, action),
        metadata={"action": action},
    )

