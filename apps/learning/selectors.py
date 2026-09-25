from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import Http404

from apps.accounts.models import User
from apps.adaptive.models import Decision
from apps.core.models import SystemSetting
from apps.curriculum.models import Lesson, QuestionChoice

from .models import Response, Session, SessionItem, StudentPath


@dataclass(frozen=True)
class AssessmentState:
    session: Session
    item: SessionItem | None
    response: Response | None
    answered_count: int
    total_count: int
    next_order: int | None


def student_path_for(student: User) -> StudentPath:
    try:
        return StudentPath.objects.select_related("current_lesson").get(student=student)
    except StudentPath.DoesNotExist as error:
        raise Http404 from error


def owned_session(student: User, session_id) -> Session:
    try:
        return Session.objects.select_related("lesson").get(pk=session_id, student=student)
    except Session.DoesNotExist as error:
        raise Http404 from error


def assessment_state(*, student: User, session_id, order: int | None = None) -> AssessmentState:
    session = owned_session(student, session_id)
    items = list(
        SessionItem.objects.filter(session=session)
        .select_related(
            "question",
            "question__skill",
            "question__video",
            "response",
            "response__selected_choice",
        )
        .prefetch_related(
            Prefetch("question__choices", queryset=QuestionChoice.objects.order_by("display_order"))
        )
        .order_by("display_order")
    )
    if not items:
        raise Http404
    answered = [item for item in items if hasattr(item, "response")]
    first_unanswered = next((item for item in items if not hasattr(item, "response")), None)
    if session.status == Session.Status.COMPLETED:
        return AssessmentState(session, None, None, len(answered), len(items), None)
    target_order = order or (first_unanswered.display_order if first_unanswered else items[-1].display_order)
    item = next((candidate for candidate in items if candidate.display_order == target_order), None)
    if item is None:
        raise Http404
    if first_unanswered and item.display_order > first_unanswered.display_order:
        raise PermissionDenied("Questions must be completed in their issued order.")
    response = item.response if hasattr(item, "response") else None
    next_order = item.display_order + 1 if item.display_order < len(items) else None
    return AssessmentState(session, item, response, len(answered), len(items), next_order)


def completed_session_responses(*, student: User, session_id) -> tuple[Session, list[SessionItem]]:
    session = owned_session(student, session_id)
    if session.status != Session.Status.COMPLETED:
        raise PermissionDenied("Results are available only after completion.")
    items = list(
        SessionItem.objects.filter(session=session)
        .select_related(
            "question",
            "question__skill",
            "response",
            "response__selected_choice",
        )
        .prefetch_related(
            Prefetch("question__choices", queryset=QuestionChoice.objects.order_by("display_order"))
        )
        .order_by("display_order")
    )
    return session, items


def lesson_is_reached(path: StudentPath, lesson: Lesson) -> bool:
    if path.status in {
        StudentPath.Status.ACTIVITY_READY,
        StudentPath.Status.POSTTEST_READY,
        StudentPath.Status.COMPLETED,
    }:
        return True
    return bool(
        path.status == StudentPath.Status.LEARNING
        and path.current_lesson
        and lesson.lesson_order <= path.current_lesson.lesson_order
    )


def my_lesson_steps(*, student: User, path: StudentPath) -> dict:
    sessions = list(
        Session.objects.filter(student=student)
        .select_related("lesson")
        .order_by("created_at")
    )
    by_type_lesson = {(item.session_type, item.lesson_id): item for item in sessions}
    decisions = list(
        Decision.objects.filter(session__student=student)
        .select_related("session")
        .order_by("created_at")
    )
    assigned_by_lesson: dict = {}
    for decision in decisions:
        if decision.session.lesson_id:
            assigned_by_lesson.setdefault(decision.session.lesson_id, set()).add(decision.action)

    lessons = []
    for lesson in Lesson.objects.filter(is_published=True).order_by("lesson_order"):
        reached = lesson_is_reached(path, lesson)
        is_current = path.current_lesson_id == lesson.pk and path.status == StudentPath.Status.LEARNING
        if not reached:
            state = "locked"
        elif is_current:
            state = "current"
        else:
            state = "completed"
        regular = by_type_lesson.get((Session.SessionType.REGULAR, lesson.pk))
        additional = by_type_lesson.get((Session.SessionType.ADDITIONAL, lesson.pk))
        foundational = by_type_lesson.get((Session.SessionType.FOUNDATIONAL, lesson.pk))
        assigned = assigned_by_lesson.get(lesson.pk, set())
        lessons.append(
            {
                "lesson": lesson,
                "state": state,
                "reached": reached,
                "regular": regular,
                "additional": additional,
                "foundational": foundational,
                "show_additional": bool(
                    additional or Decision.Action.ADDITIONAL_EXERCISE in assigned
                ),
                "show_foundational": bool(
                    foundational or Decision.Action.FOUNDATIONAL_EXERCISE in assigned
                ),
            }
        )

    setting = SystemSetting.objects.filter(singleton_key=1).first()
    pretest = by_type_lesson.get((Session.SessionType.PRETEST, None))
    activity = by_type_lesson.get((Session.SessionType.ACTIVITY, None))
    posttest = by_type_lesson.get((Session.SessionType.POSTTEST, None))
    return {
        "pretest": pretest,
        "lessons": lessons,
        "activity": activity,
        "posttest": posttest,
        "posttest_access_open": bool(setting and setting.posttest_access_enabled),
    }
