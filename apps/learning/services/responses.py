from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import is_student
from apps.core.models import SystemSetting
from apps.curriculum.models import Lesson, QuestionChoice

from .. import interfaces
from ..models import Response, Session, SessionItem, StudentPath


IMMEDIATE_FEEDBACK_TYPES = {
    Session.SessionType.REGULAR,
    Session.SessionType.ADDITIONAL,
    Session.SessionType.FOUNDATIONAL,
    Session.SessionType.ACTIVITY,
}


@dataclass(frozen=True)
class ResponseOutcome:
    response: Response
    session: Session
    duplicate: bool

    @property
    def reveal_feedback(self) -> bool:
        return self.session.session_type in IMMEDIATE_FEEDBACK_TYPES or self.session.status == Session.Status.COMPLETED

    @property
    def is_correct(self) -> bool | None:
        return self.response.is_correct if self.reveal_feedback else None


def _require_submission_access(student: User) -> SystemSetting:
    if not is_student(student):
        raise PermissionDenied
    setting = SystemSetting.objects.filter(singleton_key=1).first()
    if setting is None or not setting.study_access_enabled:
        raise PermissionDenied("Student Study Access is closed.")
    return setting


def _apply_fixed_transition(path: StudentPath, session: Session) -> None:
    if session.session_type == Session.SessionType.PRETEST:
        first_lesson = Lesson.objects.filter(is_published=True).order_by("lesson_order").first()
        if first_lesson is None:
            raise ValidationError("The first published lesson is unavailable.")
        path.status = StudentPath.Status.LEARNING
        path.current_lesson = first_lesson
        path.current_stage = StudentPath.Stage.LESSON
        path.save(update_fields=["status", "current_lesson", "current_stage", "updated_at"])
    elif session.session_type == Session.SessionType.ACTIVITY:
        path.status = StudentPath.Status.POSTTEST_READY
        path.current_stage = StudentPath.Stage.POSTTEST
        path.save(update_fields=["status", "current_stage", "updated_at"])
    elif session.session_type == Session.SessionType.POSTTEST:
        path.status = StudentPath.Status.COMPLETED
        path.current_stage = StudentPath.Stage.POSTTEST
        path.save(update_fields=["status", "current_stage", "updated_at"])
    else:
        interfaces.exercise_completed(session=session, student_path=path)


@transaction.atomic
def submit_response(
    *,
    student: User,
    session_id: UUID,
    item_id: UUID,
    choice_id: UUID,
    hint_was_revealed: bool = False,
) -> ResponseOutcome:
    setting = _require_submission_access(student)
    session = Session.objects.select_for_update().filter(pk=session_id).first()
    if session is None or session.student_id != student.pk:
        raise PermissionDenied
    if session.session_type == Session.SessionType.POSTTEST and not setting.posttest_access_enabled:
        raise PermissionDenied("Post-test Access is closed.")

    item = (
        SessionItem.objects.select_for_update()
        .select_related("question")
        .filter(pk=item_id, session=session)
        .first()
    )
    if item is None:
        raise PermissionDenied

    existing = Response.objects.select_related("selected_choice").filter(session_item=item).first()
    if existing is not None:
        return ResponseOutcome(existing, session, True)
    if session.status != Session.Status.IN_PROGRESS:
        raise ValidationError("This assessment is not accepting responses.")

    current_item = (
        SessionItem.objects.filter(session=session, response__isnull=True)
        .order_by("display_order")
        .first()
    )
    if current_item is None or current_item.pk != item.pk:
        raise ValidationError("Responses must follow the issued question order.")
    choice = QuestionChoice.objects.filter(pk=choice_id, question_id=item.question_id).first()
    if choice is None:
        raise ValidationError("The selected choice does not belong to this question.")
    if hint_was_revealed and session.session_type != Session.SessionType.FOUNDATIONAL:
        raise ValidationError("Hints are available only for foundational exercises.")

    response = Response.objects.create(
        session_item=item,
        selected_choice=choice,
        hint_used=hint_was_revealed,
        answered_at=timezone.now(),
    )
    if session.session_type != Session.SessionType.POSTTEST:
        interfaces.record_response_evidence(response=response)

    remaining = SessionItem.objects.filter(session=session, response__isnull=True).exists()
    if not remaining:
        now = timezone.now()
        path = StudentPath.objects.select_for_update().get(student=student)
        _apply_fixed_transition(path, session)
        session.status = Session.Status.COMPLETED
        session.submitted_at = now
        session.completed_at = now
        session.save(update_fields=["status", "submitted_at", "completed_at", "updated_at"])

    return ResponseOutcome(response, session, False)
