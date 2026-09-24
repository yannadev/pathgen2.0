from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_safe

from apps.accounts.models import User
from apps.accounts.admin_forms import (
    ConfirmForm as UserConfirmForm,
    DeleteUserForm,
    ManagedUserCreateForm,
    ManagedUserUpdateForm,
    RequiredReasonForm as UserReasonForm,
)
from apps.accounts.permissions import admin_required
from apps.accounts.selectors import get_visible_user_or_404, users_visible_to
from apps.accounts.services.lifecycle import (
    create_managed_user,
    deactivate_user,
    delete_unused_user,
    reactivate_user,
    update_managed_user,
)
from apps.accounts.throttling import (
    check_sensitive_throttle,
    record_sensitive_attempt,
)
from apps.classrooms.forms import (
    AddStudentsForm,
    AssignTeacherForm,
    ClassroomCreateForm,
    ClassroomUpdateForm,
    ConfirmForm as ClassConfirmForm,
    DeleteClassroomForm,
    OptionalReasonForm,
    RequiredReasonForm as ClassReasonForm,
)
from apps.classrooms.models import StudentMembership
from apps.classrooms.selectors import (
    classrooms_visible_to,
    get_visible_classroom_or_404,
)
from apps.classrooms.services.lifecycle import (
    add_students,
    archive_classroom,
    assign_teacher,
    close_membership,
    create_classroom,
    delete_unused_classroom,
    reactivate_classroom,
    update_classroom,
)
from apps.core.forms import GlobalOverrideForm
from apps.core.models import SystemSetting
from apps.core.selectors import recent_audit_events, setting_audit_history
from apps.core.services.settings import SettingsRevisionConflict, update_global_override


def _paginate(request: HttpRequest, queryset, *, per_page: int = 20):
    page_obj = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return page_obj, query.urlencode()


def _add_service_error(form, error: ValidationError) -> None:
    if hasattr(error, "message_dict"):
        for field, messages_for_field in error.message_dict.items():
            target = field if field in form.fields else None
            for message in messages_for_field:
                form.add_error(target, message)
    else:
        for message in error.messages:
            form.add_error(None, message)


def _record_sensitive_submission(request: HttpRequest, *, action: str, form) -> int | None:
    decision = check_sensitive_throttle(request, user=request.user, action=action)
    if not decision.allowed:
        form.add_error(None, "Unable to complete that request right now. Please try again later.")
        return decision.retry_after
    record_sensitive_attempt(request, user=request.user, action=action)
    return None


def _management_redirect(route_name: str, target_id=None):
    url = reverse(route_name)
    if target_id:
        url = f"{url}?target={target_id}"
    return redirect(url)


def _override_forms(setting: SystemSetting, bound: GlobalOverrideForm | None = None) -> dict:
    names = {
        GlobalOverrideForm.Action.OPEN_STUDY: "open_study_form",
        GlobalOverrideForm.Action.CLOSE_STUDY: "close_study_form",
        GlobalOverrideForm.Action.UNLOCK_POSTTEST: "unlock_posttest_form",
        GlobalOverrideForm.Action.LOCK_POSTTEST: "lock_posttest_form",
    }
    forms = {}
    for action, context_name in names.items():
        if bound is not None and bound.data.get("action") == action:
            forms[context_name] = bound
        else:
            forms[context_name] = GlobalOverrideForm(
                initial={"action": action, "revision": setting.revision},
                auto_id=f"id_{action}_%s",
            )
    return forms


def _override_context(
    setting: SystemSetting,
    *,
    bound: GlobalOverrideForm | None = None,
    conflict_action: str = "",
) -> dict:
    return {
        "setting": setting,
        "audit_preview": setting_audit_history()[:8],
        "conflict_action": conflict_action,
        "breadcrumbs": [("", "Overrides")],
        **_override_forms(setting, bound),
    }


@never_cache
@admin_required
@require_safe
def dashboard(request: HttpRequest) -> HttpResponse:
    setting = SystemSetting.objects.select_related("changed_by").get(singleton_key=1)
    return render(
        request,
        "admin/admin_dashboard.html",
        {"setting": setting, "breadcrumbs": [("", "Dashboard")]},
    )


@never_cache
@admin_required
@require_safe
def users(request: HttpRequest) -> HttpResponse:
    selected = None
    target_id = request.GET.get("target")
    if target_id:
        selected = get_visible_user_or_404(actor=request.user, user_id=target_id)
    return _render_users_page(
        request,
        selected=selected,
        dialog=request.GET.get("dialog", ""),
    )


def _render_users_page(
    request: HttpRequest,
    *,
    selected: User | None = None,
    dialog: str = "",
    bound_form=None,
    status: int = 200,
) -> HttpResponse:
    queryset = users_visible_to(request.user).order_by("role", "last_name", "first_name", "username")
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "").strip()
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if role in {User.Role.TEACHER, User.Role.STUDENT}:
        queryset = queryset.filter(role=role)
    page_obj, pagination_query = _paginate(request, queryset)
    create_form = bound_form if dialog == "create" else ManagedUserCreateForm(prefix="create")
    update_form = None
    deactivate_form = None
    reactivate_form = None
    delete_form = None
    if selected is not None:
        update_form = (
            bound_form
            if dialog == "update"
            else ManagedUserUpdateForm(
                initial={
                    "first_name": selected.first_name,
                    "last_name": selected.last_name,
                    "email": selected.email,
                },
                prefix="update",
            )
        )
        deactivate_form = bound_form if dialog == "deactivate" else UserReasonForm(prefix="deactivate")
        reactivate_form = bound_form if dialog == "reactivate" else UserConfirmForm(prefix="reactivate")
        delete_form = bound_form if dialog == "delete" else DeleteUserForm(prefix="delete")
    return render(
        request,
        "admin/user_management.html",
        {
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "query": query,
            "selected_role": role,
            "selected_user": selected,
            "active_dialog": dialog,
            "create_form": create_form,
            "update_form": update_form,
            "deactivate_form": deactivate_form,
            "reactivate_form": reactivate_form,
            "delete_form": delete_form,
            "breadcrumbs": [("", "Users")],
        },
        status=status,
    )


@never_cache
@admin_required
@require_http_methods(["POST"])
def user_create(request: HttpRequest) -> HttpResponse:
    form = ManagedUserCreateForm(request.POST, prefix="create")
    retry_after = _record_sensitive_submission(request, action="admin.user_create", form=form)
    if retry_after is None and form.is_valid():
        try:
            created = create_managed_user(
                actor=request.user,
                role=form.cleaned_data["role"],
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
            )
        except ValidationError as error:
            _add_service_error(form, error)
        else:
            messages.success(request, f"Created {created.get_role_display().lower()} account {created.username}.")
            return _management_redirect("admin_portal:users", created.pk)
    response = _render_users_page(request, dialog="create", bound_form=form, status=429 if retry_after else 400)
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@admin_required
@require_http_methods(["POST"])
def user_action(request: HttpRequest, user_id, action: str) -> HttpResponse:
    target = get_visible_user_or_404(actor=request.user, user_id=user_id)
    form_classes = {
        "update": ManagedUserUpdateForm,
        "deactivate": UserReasonForm,
        "reactivate": UserConfirmForm,
        "delete": DeleteUserForm,
    }
    form_class = form_classes.get(action)
    if form_class is None:
        raise Http404
    form = form_class(request.POST, prefix=action)
    retry_after = _record_sensitive_submission(
        request, action=f"admin.user_{action}", form=form
    )
    if retry_after is None and form.is_valid():
        try:
            if action == "update":
                update_managed_user(
                    actor=request.user,
                    target=target,
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    email=form.cleaned_data["email"],
                )
                message = f"Updated {target.username}."
            elif action == "deactivate":
                deactivate_user(
                    actor=request.user,
                    target=target,
                    reason=form.cleaned_data["reason"],
                )
                message = f"Deactivated {target.username}."
            elif action == "reactivate":
                reactivate_user(actor=request.user, target=target)
                message = f"Reactivated {target.username}."
            else:
                delete_unused_user(
                    actor=request.user,
                    target=target,
                    confirmed_username=form.cleaned_data["username_confirmation"],
                    reason=form.cleaned_data["reason"],
                )
                message = f"Deleted unused account {target.username}."
        except ValidationError as error:
            _add_service_error(form, error)
        else:
            messages.success(request, message)
            return _management_redirect(
                "admin_portal:users", None if action == "delete" else target.pk
            )
    response = _render_users_page(
        request,
        selected=target,
        dialog=action,
        bound_form=form,
        status=429 if retry_after else 400,
    )
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@admin_required
@require_safe
def classes(request: HttpRequest) -> HttpResponse:
    selected = None
    selected_membership = None
    target_id = request.GET.get("target")
    if target_id:
        selected = get_visible_classroom_or_404(actor=request.user, classroom_id=target_id)
        membership_id = request.GET.get("membership")
        if membership_id:
            selected_membership = get_object_or_404(
                StudentMembership.objects.select_related("student"),
                pk=membership_id,
                classroom=selected,
            )
    return _render_classes_page(
        request,
        selected=selected,
        selected_membership=selected_membership,
        dialog=request.GET.get("dialog", ""),
    )


def _render_classes_page(
    request: HttpRequest,
    *,
    selected=None,
    selected_membership=None,
    dialog: str = "",
    bound_form=None,
    status: int = 200,
) -> HttpResponse:
    queryset = classrooms_visible_to(request.user).select_related("teacher").order_by("code")
    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    if query:
        queryset = queryset.filter(Q(code__icontains=query) | Q(name__icontains=query))
    if selected_status in {"active", "archived"}:
        queryset = queryset.filter(status=selected_status)
    page_obj, pagination_query = _paginate(request, queryset)
    create_form = bound_form if dialog == "create" else ClassroomCreateForm(prefix="create")
    update_form = assign_form = add_students_form = archive_form = None
    reactivate_form = delete_form = remove_student_form = None
    memberships = StudentMembership.objects.none()
    if selected is not None:
        memberships = selected.student_memberships.select_related("student").order_by(
            "-joined_at"
        )
        update_form = (
            bound_form
            if dialog == "update"
            else ClassroomUpdateForm(
                initial={"code": selected.code, "name": selected.name}, prefix="update"
            )
        )
        assign_form = (
            bound_form
            if dialog == "assign"
            else AssignTeacherForm(initial={"teacher": selected.teacher_id}, prefix="assign")
        )
        add_students_form = (
            bound_form
            if dialog == "add_students"
            else AddStudentsForm(classroom=selected, prefix="add_students")
        )
        archive_form = bound_form if dialog == "archive" else ClassReasonForm(prefix="archive")
        reactivate_form = bound_form if dialog == "reactivate" else ClassConfirmForm(prefix="reactivate")
        delete_form = bound_form if dialog == "delete" else DeleteClassroomForm(prefix="delete")
        remove_student_form = (
            bound_form if dialog == "remove_student" else OptionalReasonForm(prefix="remove_student")
        )
    return render(
        request,
        "admin/class_management.html",
        {
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "query": query,
            "selected_status": selected_status,
            "selected_class": selected,
            "selected_membership": selected_membership,
            "memberships": memberships,
            "active_dialog": dialog,
            "create_form": create_form,
            "update_form": update_form,
            "assign_form": assign_form,
            "add_students_form": add_students_form,
            "archive_form": archive_form,
            "reactivate_form": reactivate_form,
            "delete_form": delete_form,
            "remove_student_form": remove_student_form,
            "breadcrumbs": [("", "Classes")],
        },
        status=status,
    )


@never_cache
@admin_required
@require_http_methods(["POST"])
def class_create(request: HttpRequest) -> HttpResponse:
    form = ClassroomCreateForm(request.POST, prefix="create")
    retry_after = _record_sensitive_submission(request, action="admin.class_create", form=form)
    if retry_after is None and form.is_valid():
        try:
            created = create_classroom(
                actor=request.user,
                code=form.cleaned_data["code"],
                name=form.cleaned_data["name"],
                teacher=form.cleaned_data["teacher"],
            )
        except ValidationError as error:
            _add_service_error(form, error)
        else:
            messages.success(request, f"Created class {created.code}.")
            return _management_redirect("admin_portal:classes", created.pk)
    response = _render_classes_page(request, dialog="create", bound_form=form, status=429 if retry_after else 400)
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@admin_required
@require_http_methods(["POST"])
def class_action(request: HttpRequest, classroom_id, action: str) -> HttpResponse:
    classroom = get_visible_classroom_or_404(actor=request.user, classroom_id=classroom_id)
    form_factories = {
        "update": lambda: ClassroomUpdateForm(request.POST, prefix="update"),
        "assign": lambda: AssignTeacherForm(request.POST, prefix="assign"),
        "add_students": lambda: AddStudentsForm(
            request.POST, classroom=classroom, prefix="add_students"
        ),
        "archive": lambda: ClassReasonForm(request.POST, prefix="archive"),
        "reactivate": lambda: ClassConfirmForm(request.POST, prefix="reactivate"),
        "delete": lambda: DeleteClassroomForm(request.POST, prefix="delete"),
    }
    factory = form_factories.get(action)
    if factory is None:
        raise Http404
    form = factory()
    retry_after = _record_sensitive_submission(
        request, action=f"admin.class_{action}", form=form
    )
    if retry_after is None and form.is_valid():
        try:
            if action == "update":
                update_classroom(
                    actor=request.user,
                    classroom=classroom,
                    code=form.cleaned_data["code"],
                    name=form.cleaned_data["name"],
                )
                message = f"Updated class {classroom.code}."
            elif action == "assign":
                assign_teacher(
                    actor=request.user,
                    classroom=classroom,
                    teacher=form.cleaned_data["teacher"],
                )
                message = f"Updated the teacher assignment for {classroom.code}."
            elif action == "add_students":
                created = add_students(
                    actor=request.user,
                    classroom=classroom,
                    students=form.cleaned_data["students"],
                )
                message = f"Added {len(created)} student{'s' if len(created) != 1 else ''} to {classroom.code}."
            elif action == "archive":
                archive_classroom(
                    actor=request.user,
                    classroom=classroom,
                    reason=form.cleaned_data["reason"],
                )
                message = f"Archived class {classroom.code}."
            elif action == "reactivate":
                reactivate_classroom(actor=request.user, classroom=classroom)
                message = f"Reactivated class {classroom.code}."
            else:
                delete_unused_classroom(
                    actor=request.user,
                    classroom=classroom,
                    confirmed_code=form.cleaned_data["code_confirmation"],
                    reason=form.cleaned_data["reason"],
                )
                message = f"Deleted unused class {classroom.code}."
        except ValidationError as error:
            _add_service_error(form, error)
        else:
            messages.success(request, message)
            return _management_redirect(
                "admin_portal:classes", None if action == "delete" else classroom.pk
            )
    response = _render_classes_page(
        request,
        selected=classroom,
        dialog=action,
        bound_form=form,
        status=429 if retry_after else 400,
    )
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@admin_required
@require_http_methods(["POST"])
def membership_remove(request: HttpRequest, classroom_id, membership_id) -> HttpResponse:
    classroom = get_visible_classroom_or_404(actor=request.user, classroom_id=classroom_id)
    membership = get_object_or_404(
        StudentMembership.objects.select_related("student"),
        pk=membership_id,
        classroom=classroom,
    )
    form = OptionalReasonForm(request.POST, prefix="remove_student")
    retry_after = _record_sensitive_submission(
        request, action="admin.membership_remove", form=form
    )
    if retry_after is None and form.is_valid():
        try:
            close_membership(
                actor=request.user,
                membership=membership,
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            _add_service_error(form, error)
        else:
            messages.success(request, f"Closed {membership.student.username}'s membership.")
            return _management_redirect("admin_portal:classes", classroom.pk)
    response = _render_classes_page(
        request,
        selected=classroom,
        selected_membership=membership,
        dialog="remove_student",
        bound_form=form,
        status=429 if retry_after else 400,
    )
    if retry_after:
        response["Retry-After"] = str(retry_after)
    return response


@never_cache
@admin_required
@require_http_methods(["GET", "POST"])
def overrides(request: HttpRequest) -> HttpResponse:
    setting = SystemSetting.objects.select_related("changed_by").get(singleton_key=1)
    if request.method == "GET":
        return render(request, "admin/override.html", _override_context(setting))

    throttle = check_sensitive_throttle(
        request,
        user=request.user,
        action="global_override",
    )
    submitted_action = request.POST.get("action", "override")
    form = GlobalOverrideForm(request.POST, auto_id=f"id_{submitted_action}_%s")
    if not throttle.allowed:
        form.add_error(None, "Unable to complete that request right now. Please try again later.")
        response = render(
            request,
            "admin/override.html",
            _override_context(setting, bound=form, conflict_action=request.POST.get("action", "")),
            status=429,
        )
        response["Retry-After"] = str(throttle.retry_after)
        return response

    record_sensitive_attempt(request, user=request.user, action="global_override")
    if not form.is_valid():
        return render(
            request,
            "admin/override.html",
            _override_context(setting, bound=form, conflict_action=request.POST.get("action", "")),
            status=400,
        )

    field, enabled = form.setting_change()
    try:
        updated = update_global_override(
            actor=request.user,
            field=field,
            enabled=enabled,
            expected_revision=form.cleaned_data["revision"],
            reason=form.cleaned_data["reason"],
        )
    except SettingsRevisionConflict as conflict:
        form.add_error(
            None,
            "Another administrator changed access settings. Review the current state and confirm again.",
        )
        form.data = form.data.copy()
        form.data["revision"] = conflict.current.revision
        return render(
            request,
            "admin/override.html",
            _override_context(
                conflict.current,
                bound=form,
                conflict_action=form.cleaned_data["action"],
            ),
            status=409,
        )
    except ValidationError as error:
        if hasattr(error, "message_dict") and "reason" in error.message_dict:
            for message in error.message_dict["reason"]:
                form.add_error("reason", message)
        else:
            form.add_error(None, error.messages[0])
        return render(
            request,
            "admin/override.html",
            _override_context(setting, bound=form, conflict_action=form.cleaned_data["action"]),
            status=400,
        )

    label = "Student Study Access" if field == "study_access_enabled" else "Post-test Access"
    if field == "study_access_enabled":
        state_label = "open" if getattr(updated, field) else "closed"
    else:
        state_label = "unlocked" if getattr(updated, field) else "locked"
    messages.success(request, f"{label} is now {state_label}.")
    return redirect("admin_portal:overrides")


@never_cache
@admin_required
@require_safe
def audit_logs(request: HttpRequest) -> HttpResponse:
    page_obj, pagination_query = _paginate(request, recent_audit_events())
    return render(
        request,
        "admin/audit_logs.html",
        {
            "page_obj": page_obj,
            "pagination_query": pagination_query,
            "breadcrumbs": [("", "Audit Logs")],
        },
    )
