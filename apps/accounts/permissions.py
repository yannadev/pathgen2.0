from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from apps.accounts.models import User


P = ParamSpec("P")
R = TypeVar("R", bound=HttpResponse)


def has_role(user: User, *roles: str) -> bool:
    return bool(user.is_authenticated and user.is_active and user.role in roles)


def is_admin(user: User) -> bool:
    return has_role(user, User.Role.ADMIN)


def is_teacher(user: User) -> bool:
    return has_role(user, User.Role.TEACHER)


def is_student(user: User) -> bool:
    return has_role(user, User.Role.STUDENT)


def require_admin(user: User) -> None:
    if not is_admin(user):
        raise PermissionDenied


def role_required(*roles: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    allowed_roles = frozenset(roles)

    def decorator(view: Callable[P, R]) -> Callable[P, R]:
        @wraps(view)
        def wrapped(request: HttpRequest, *args: P.args, **kwargs: P.kwargs) -> R:
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())  # type: ignore[return-value]
            if not has_role(request.user, *allowed_roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


admin_required = role_required(User.Role.ADMIN)
teacher_required = role_required(User.Role.TEACHER)
student_required = role_required(User.Role.STUDENT)

