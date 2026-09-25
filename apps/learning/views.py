from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe

from apps.accounts.permissions import student_required
from apps.curriculum.models import Lesson
from apps.curriculum.selectors import published_lesson_previews

from .models import Session, StudentPath
from .selectors import (
    assessment_state,
    completed_session_responses,
    lesson_is_reached,
    my_lesson_steps,
    owned_session,
)
from .services import complete_lesson_content, ensure_student_path, issue_session, submit_response


ASSESSMENT_TEMPLATES = {
    Session.SessionType.PRETEST: "assessment/pretest.html",
    Session.SessionType.REGULAR: "assessment/exercise.html",
    Session.SessionType.ADDITIONAL: "assessment/exercise.html",
    Session.SessionType.FOUNDATIONAL: "assessment/exercise.html",
    Session.SessionType.ACTIVITY: "assessment/activity.html",
    Session.SessionType.POSTTEST: "assessment/posttest.html",
}
ITEM_COUNTS = {
    Session.SessionType.PRETEST: 30,
    Session.SessionType.REGULAR: 10,
    Session.SessionType.ADDITIONAL: 10,
    Session.SessionType.FOUNDATIONAL: "5 per assigned skill",
    Session.SessionType.ACTIVITY: 15,
    Session.SessionType.POSTTEST: 30,
}


def _assessment_template(session_type: str) -> str:
    try:
        return ASSESSMENT_TEMPLATES[session_type]
    except KeyError as error:
        raise Http404 from error


def _existing_for_path(request: HttpRequest, session_type: str) -> Session | None:
    path = ensure_student_path(student=request.user)
    lesson = path.current_lesson if session_type in {
        Session.SessionType.REGULAR,
        Session.SessionType.ADDITIONAL,
        Session.SessionType.FOUNDATIONAL,
    } else None
    return (
        Session.objects.filter(
            student=request.user,
            session_type=session_type,
            lesson=lesson,
            attempt_number=1,
        )
        .order_by("created_at")
        .first()
    )


@never_cache
@student_required
@require_safe
def my_lesson(request: HttpRequest) -> HttpResponse:
    path = ensure_student_path(student=request.user)
    return render(
        request,
        "student/my_lesson.html",
        {
            "student_path": path,
            **my_lesson_steps(student=request.user, path=path),
            "breadcrumbs": [("", "My Lesson")],
        },
    )


@never_cache
@student_required
@require_safe
def lesson_detail(request: HttpRequest, lesson_slug: str) -> HttpResponse:
    path = ensure_student_path(student=request.user)
    lesson = get_object_or_404(Lesson, slug=lesson_slug, is_published=True)
    if not lesson_is_reached(path, lesson):
        raise PermissionDenied
    preview = next((item for item in published_lesson_previews() if item.pk == lesson.pk), None)
    if preview is None:
        raise Http404
    can_continue = (
        path.status == StudentPath.Status.LEARNING
        and path.current_stage == StudentPath.Stage.LESSON
        and path.current_lesson_id == lesson.pk
    )
    return render(
        request,
        "student/lesson.html",
        {
            "lesson": preview,
            "can_continue": can_continue,
            "breadcrumbs": [
                (reverse("learning:my_lesson"), "My Lesson"),
                ("", f"Lesson {lesson.lesson_order}"),
            ],
        },
    )


@never_cache
@student_required
@require_POST
def lesson_complete(request: HttpRequest, lesson_slug: str) -> HttpResponse:
    lesson = get_object_or_404(Lesson, slug=lesson_slug, is_published=True)
    complete_lesson_content(student=request.user, lesson=lesson)
    return redirect("learning:assessment_overview", session_type=Session.SessionType.REGULAR)


@never_cache
@student_required
@require_safe
def assessment_overview(request: HttpRequest, session_type: str) -> HttpResponse:
    template = _assessment_template(session_type)
    existing = _existing_for_path(request, session_type)
    return render(
        request,
        template,
        {
            "view_state": "overview",
            "session_type": session_type,
            "session_label": dict(Session.SessionType.choices)[session_type],
            "item_count": ITEM_COUNTS[session_type],
            "existing_session": existing,
        },
    )


@never_cache
@student_required
@require_POST
def assessment_start(request: HttpRequest, session_type: str) -> HttpResponse:
    _assessment_template(session_type)
    try:
        session = issue_session(student=request.user, session_type=session_type)
    except ValidationError as error:
        return render(
            request,
            ASSESSMENT_TEMPLATES[session_type],
            {
                "view_state": "overview",
                "session_type": session_type,
                "session_label": dict(Session.SessionType.choices)[session_type],
                "item_count": ITEM_COUNTS[session_type],
                "workflow_error": error.messages[0],
            },
            status=400,
        )
    if session.status == Session.Status.COMPLETED:
        return redirect("learning:assessment_result", session_id=session.pk)
    return redirect("learning:assessment_question", session_id=session.pk, order=1)


def _question_context(request: HttpRequest, session_id, order: int) -> dict:
    state = assessment_state(student=request.user, session_id=session_id, order=order)
    session = state.session
    if state.item is None:
        return {"redirect_result": True, "session": session}
    item = state.item
    hint_key = f"assessment_hint:{session.pk}:{item.pk}"
    hint_revealed = bool(request.session.get(hint_key))
    response = state.response
    reveal_feedback = bool(
        response
        and session.session_type
        in {
            Session.SessionType.REGULAR,
            Session.SessionType.ADDITIONAL,
            Session.SessionType.FOUNDATIONAL,
            Session.SessionType.ACTIVITY,
        }
    )
    embed_url = ""
    if item.question.video_id:
        embed_url = (
            f"https://www.youtube-nocookie.com/embed/{item.question.video.youtube_video_id}"
            "?enablejsapi=1&rel=0&cc_load_policy=1"
        )
    return {
        "view_state": "assessment",
        "session": session,
        "session_type": session.session_type,
        "session_label": session.get_session_type_display(),
        "item": item,
        "question": item.question,
        "response": response,
        "reveal_feedback": reveal_feedback,
        "hint_revealed": hint_revealed,
        "answered_count": state.answered_count,
        "total_count": state.total_count,
        "next_order": state.next_order,
        "video_embed_url": embed_url,
    }


@never_cache
@student_required
@require_safe
def assessment_question(request: HttpRequest, session_id, order: int) -> HttpResponse:
    context = _question_context(request, session_id, order)
    if context.get("redirect_result"):
        return redirect("learning:assessment_result", session_id=session_id)
    return render(request, _assessment_template(context["session_type"]), context)


@never_cache
@student_required
@require_POST
def assessment_answer(request: HttpRequest, session_id, item_id) -> HttpResponse:
    session = owned_session(request.user, session_id)
    item = get_object_or_404(session.items, pk=item_id)
    hint_key = f"assessment_hint:{session.pk}:{item.pk}"
    try:
        outcome = submit_response(
            student=request.user,
            session_id=session.pk,
            item_id=item.pk,
            choice_id=request.POST.get("choice", ""),
            hint_was_revealed=bool(request.session.get(hint_key)),
        )
    except ValidationError as error:
        context = _question_context(request, session.pk, item.display_order)
        context["answer_error"] = error.messages[0]
        return render(request, _assessment_template(session.session_type), context, status=400)
    request.session.pop(hint_key, None)
    messages.success(request, "Your answer was saved and locked.")
    if outcome.session.status == Session.Status.COMPLETED:
        return redirect("learning:assessment_result", session_id=session.pk)
    return redirect(
        "learning:assessment_question",
        session_id=session.pk,
        order=item.display_order,
    )


@never_cache
@student_required
@require_POST
def assessment_hint(request: HttpRequest, session_id, item_id) -> HttpResponse:
    session = owned_session(request.user, session_id)
    if session.session_type != Session.SessionType.FOUNDATIONAL:
        raise PermissionDenied
    item = get_object_or_404(session.items.select_related("question"), pk=item_id)
    state = assessment_state(student=request.user, session_id=session.pk, order=item.display_order)
    if state.response is not None or not item.question.hint:
        raise PermissionDenied
    request.session[f"assessment_hint:{session.pk}:{item.pk}"] = True
    return redirect(
        "learning:assessment_question",
        session_id=session.pk,
        order=item.display_order,
    )


@never_cache
@student_required
@require_safe
def assessment_result(request: HttpRequest, session_id) -> HttpResponse:
    session, items = completed_session_responses(student=request.user, session_id=session_id)
    return render(
        request,
        _assessment_template(session.session_type),
        {
            "view_state": "result",
            "session": session,
            "session_type": session.session_type,
            "session_label": session.get_session_type_display(),
            "items": items,
        },
    )
