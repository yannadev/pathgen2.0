from __future__ import annotations

import logging
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import LoginForm, OwnNameForm, OwnPasswordChangeForm
from apps.accounts.middleware import initialize_session_lifetime
from apps.accounts.models import User
from apps.accounts.sessions import invalidate_user_sessions
from apps.accounts.throttling import (
    check_login_throttle,
    check_sensitive_throttle,
    record_login_throttle_event,
    record_sensitive_attempt,
)
from apps.core.models import SystemSetting
from apps.core.services.audit import record_model_audit_event
from apps.core.services.settings import initialize_system_setting


logger = logging.getLogger(__name__)
GENERIC_THROTTLE_ERROR = "Unable to complete that request right now. Please try again later."
COMMON_NEXT_VIEWS = frozenset(
    {
        "account:my_account",
        "account:update_name",
        "account:update_password",
        "account:logout",
    }
)


def _student_study_access_is_open() -> bool:
    return SystemSetting.objects.filter(
        singleton_key=1,
        study_access_enabled=True,
    ).exists()


def _safe_next_url(request: HttpRequest, user: User) -> str | None:
    candidate = request.POST.get("next") or request.GET.get("next")
    if not candidate or not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None
    try:
        match = resolve(urlsplit(candidate).path)
    except Exception:
        return None
    if match.view_name not in COMMON_NEXT_VIEWS:
        return None
    return candidate


def _audit_login_failure(username: str) -> None:
    user = User.objects.filter(username=username).only("id", "role", "is_active").first()
    if user is None:
        return
    action = "auth.login_denied_inactive" if not user.is_active else "auth.login_failed"
    record_model_audit_event(
        action=action,
        target=user,
        target_snapshot={"role": user.role, "is_active": user.is_active},
    )


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("account:my_account")
    form = LoginForm(request=request, data=request.POST or None)
    status = 200
    retry_after = 0
    if request.method == "POST":
        username = request.POST.get("username", "")
        throttle = check_login_throttle(request, username)
        if not throttle.allowed:
            form.add_error(None, GENERIC_THROTTLE_ERROR)
            status = 429
            retry_after = throttle.retry_after
            logger.warning("Login request throttled.")
        elif form.is_valid():
            user = form.get_user()
            if user.role == User.Role.STUDENT and not _student_study_access_is_open():
                record_login_throttle_event(request, username, succeeded=True, actor=user)
                record_model_audit_event(
                    actor=user,
                    action="auth.login_denied_study_access",
                    target=user,
                    target_snapshot={"role": user.role, "is_active": user.is_active},
                )
                form.add_error(
                    None,
                    "Student Study Access is currently closed. Contact your administrator for help.",
                )
                status = 403
            else:
                auth_login(request, user)
                initialize_session_lifetime(request)
                if user.role == User.Role.ADMIN:
                    initialize_system_setting(actor=user)
                record_login_throttle_event(request, username, succeeded=True, actor=user)
                record_model_audit_event(
                    actor=user,
                    action="auth.login_succeeded",
                    target=user,
                    target_snapshot={"role": user.role, "is_active": user.is_active},
                )
                default_url = (
                    reverse("admin_portal:dashboard")
                    if user.role == User.Role.ADMIN
                    else reverse("account:my_account")
                )
                return HttpResponseRedirect(_safe_next_url(request, user) or default_url)
        else:
            record_login_throttle_event(request, username, succeeded=False)
            _audit_login_failure(username)
            mutable_data = form.data.copy()
            mutable_data["username"] = ""
            form.data = mutable_data
    if form.errors:
        form.fields["username"].widget.attrs.pop("autofocus", None)
    response = render(
        request,
        "account/login.html",
        {"form": form, "next": request.POST.get("next") or request.GET.get("next", "")},
        status=status,
    )
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@login_required
@require_http_methods(["GET"])
def my_account(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "account/my_account.html",
        {"breadcrumbs": [("", "My Account")]},
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def update_name(request: HttpRequest) -> HttpResponse:
    form = OwnNameForm(request.POST or None, instance=request.user)
    status = 200
    if request.method == "POST":
        throttle = check_sensitive_throttle(request, user=request.user, action="name_change")
        if not throttle.allowed:
            form.add_error(None, GENERIC_THROTTLE_ERROR)
            status = 429
        else:
            record_sensitive_attempt(request, user=request.user, action="name_change")
            if form.is_valid():
                changed_fields = list(form.changed_data)
                user = form.save()
                if changed_fields:
                    record_model_audit_event(
                        actor=user,
                        action="user.name_updated",
                        target=user,
                        target_snapshot={"changed_fields": changed_fields},
                    )
                messages.success(request, "Your name was updated.")
                return redirect("account:my_account")
    return render(
        request,
        "account/update_name.html",
        {
            "form": form,
            "breadcrumbs": [
                (reverse("account:my_account"), "My Account"),
                ("", "Change name"),
            ],
        },
        status=status,
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def update_password(request: HttpRequest) -> HttpResponse:
    form = OwnPasswordChangeForm(user=request.user, data=request.POST or None)
    status = 200
    if request.method == "POST":
        throttle = check_sensitive_throttle(request, user=request.user, action="password_change")
        if not throttle.allowed:
            form.add_error(None, GENERIC_THROTTLE_ERROR)
            status = 429
        else:
            record_sensitive_attempt(request, user=request.user, action="password_change")
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                initialize_session_lifetime(request)
                invalidated_sessions = invalidate_user_sessions(
                    user,
                    exclude_session_key=request.session.session_key,
                )
                record_model_audit_event(
                    actor=user,
                    action="user.password_changed",
                    target=user,
                    target_snapshot={"role": user.role},
                    metadata={"invalidated_sessions": invalidated_sessions},
                )
                messages.success(request, "Your password was changed securely.")
                return redirect("account:my_account")
    return render(
        request,
        "account/update_password.html",
        {
            "form": form,
            "breadcrumbs": [
                (reverse("account:my_account"), "My Account"),
                ("", "Change password"),
            ],
        },
        status=status,
    )


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def logout_view(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(
            request,
            "auth/logout_confirm.html",
            {"breadcrumbs": [("", "Logout")]},
        )
    user = request.user
    record_model_audit_event(
        actor=user,
        action="auth.logout",
        target=user,
        target_snapshot={"role": user.role},
    )
    auth_logout(request)
    return redirect("account:login")
