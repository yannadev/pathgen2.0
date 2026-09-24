from __future__ import annotations

from django.contrib.auth import password_validation
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import is_admin
from apps.accounts.sessions import invalidate_user_sessions
from apps.core.services.audit import record_audit_event, record_model_audit_event


MANAGED_ROLES = frozenset({User.Role.TEACHER, User.Role.STUDENT})


def _require_admin_actor(actor: User) -> None:
    if not is_admin(actor):
        raise PermissionDenied


def _require_managed_target(target: User) -> None:
    if target.role not in MANAGED_ROLES:
        raise ValidationError("Only teacher and student accounts use this lifecycle.")


@transaction.atomic
def create_managed_user(
    *,
    actor: User,
    role: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
    email: str = "",
) -> User:
    _require_admin_actor(actor)
    if role not in MANAGED_ROLES:
        raise ValidationError("Only teacher or student accounts can be created.")
    user = User(
        username=User.normalize_username(username.strip()),
        role=role,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=User.objects.normalize_email(email.strip()),
        is_active=True,
    )
    if not user.first_name or not user.last_name:
        raise ValidationError("First and last name are required.")
    password_validation.validate_password(password, user=user)
    user.set_password(password)
    user.full_clean()
    user.save()
    record_model_audit_event(
        actor=actor,
        action="user.created",
        target=user,
        target_snapshot={"role": user.role, "is_active": user.is_active},
    )
    return user


@transaction.atomic
def deactivate_user(*, actor: User, target: User, reason: str) -> User:
    _require_admin_actor(actor)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValidationError("A deactivation reason is required.")
    locked_target = User.objects.select_for_update().get(pk=target.pk)
    _require_managed_target(locked_target)
    if not locked_target.is_active:
        raise ValidationError("The account is already inactive.")
    locked_target.is_active = False
    locked_target.deactivated_at = timezone.now()
    locked_target.deactivated_by = actor
    locked_target.deactivation_reason = normalized_reason
    locked_target.save(
        update_fields=[
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deactivation_reason",
            "updated_at",
        ]
    )
    invalidated_sessions = invalidate_user_sessions(locked_target)
    record_model_audit_event(
        actor=actor,
        action="user.deactivated",
        target=locked_target,
        target_snapshot={"role": locked_target.role, "is_active": False},
        reason=normalized_reason,
        metadata={"invalidated_sessions": invalidated_sessions},
    )
    return locked_target


@transaction.atomic
def reactivate_user(*, actor: User, target: User) -> User:
    _require_admin_actor(actor)
    locked_target = User.objects.select_for_update().get(pk=target.pk)
    _require_managed_target(locked_target)
    if locked_target.is_active:
        raise ValidationError("The account is already active.")
    locked_target.is_active = True
    locked_target.deactivated_at = None
    locked_target.deactivated_by = None
    locked_target.deactivation_reason = None
    locked_target.save(
        update_fields=[
            "is_active",
            "deactivated_at",
            "deactivated_by",
            "deactivation_reason",
            "updated_at",
        ]
    )
    record_model_audit_event(
        actor=actor,
        action="user.reactivated",
        target=locked_target,
        target_snapshot={"role": locked_target.role, "is_active": True},
    )
    return locked_target


@transaction.atomic
def update_managed_user(
    *,
    actor: User,
    target: User,
    first_name: str,
    last_name: str,
    email: str = "",
) -> User:
    _require_admin_actor(actor)
    locked_target = User.objects.select_for_update().get(pk=target.pk)
    _require_managed_target(locked_target)
    values = {
        "first_name": first_name.strip(),
        "last_name": last_name.strip(),
        "email": User.objects.normalize_email(email.strip()),
    }
    if not values["first_name"] or not values["last_name"]:
        raise ValidationError("First and last name are required.")
    changed_fields = [
        field for field, value in values.items() if getattr(locked_target, field) != value
    ]
    if not changed_fields:
        return locked_target
    for field, value in values.items():
        setattr(locked_target, field, value)
    locked_target.full_clean()
    locked_target.save(update_fields=[*changed_fields, "updated_at"])
    record_model_audit_event(
        actor=actor,
        action="user.updated",
        target=locked_target,
        target_snapshot={"role": locked_target.role, "is_active": locked_target.is_active},
        metadata={"changed_fields": changed_fields},
    )
    return locked_target


def _user_has_protected_history(target: User) -> bool:
    if target.classroom_memberships.exists():
        return True
    if target.taught_classrooms.exists():
        return True
    if hasattr(target, "learning_path"):
        return True
    if target.learning_sessions.exists():
        return True
    if target.skill_masteries.exists():
        return True
    return False


@transaction.atomic
def delete_unused_user(
    *, actor: User, target: User, confirmed_username: str, reason: str
) -> None:
    _require_admin_actor(actor)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValidationError("A deletion reason is required.")
    locked_target = User.objects.select_for_update().get(pk=target.pk)
    _require_managed_target(locked_target)
    if locked_target.is_active:
        raise ValidationError("Deactivate the account before requesting permanent deletion.")
    if confirmed_username.strip() != locked_target.username:
        raise ValidationError("Enter the exact username to confirm deletion.")
    if _user_has_protected_history(locked_target):
        raise ValidationError("Protected learning, class, or monitoring history prevents deletion.")

    target_id = locked_target.pk
    snapshot = {
        "username": locked_target.username,
        "role": locked_target.role,
        "is_active": locked_target.is_active,
    }
    try:
        locked_target.delete()
    except ProtectedError as error:
        raise ValidationError("Protected history prevents deletion of this account.") from error
    record_audit_event(
        actor=actor,
        action="user.deleted",
        target_type="accounts.user",
        target_id=target_id,
        target_snapshot=snapshot,
        reason=normalized_reason,
    )
