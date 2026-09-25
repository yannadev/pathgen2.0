from __future__ import annotations

from collections import Counter

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import is_student
from apps.adaptive.models import DecisionTargetSkill
from apps.core.models import SystemSetting
from apps.curriculum.models import Question, QuestionSet, QuestionSetItem

from ..models import Session, SessionItem, StudentPath


EXPECTED_COUNTS = {
    Session.SessionType.PRETEST: 30,
    Session.SessionType.REGULAR: 10,
    Session.SessionType.ADDITIONAL: 10,
    Session.SessionType.ACTIVITY: 15,
    Session.SessionType.POSTTEST: 30,
}


def _require_access(student: User, session_type: str) -> SystemSetting:
    if not is_student(student):
        raise PermissionDenied
    setting = SystemSetting.objects.filter(singleton_key=1).first()
    if setting is None or not setting.study_access_enabled:
        raise PermissionDenied("Student Study Access is closed.")
    if session_type == Session.SessionType.POSTTEST and not setting.posttest_access_enabled:
        raise PermissionDenied("Post-test Access is closed.")
    return setting


def _validate_path(path: StudentPath, session_type: str) -> None:
    expected = {
        Session.SessionType.PRETEST: (StudentPath.Status.PRETEST_REQUIRED, StudentPath.Stage.PRETEST),
        Session.SessionType.REGULAR: (StudentPath.Status.LEARNING, StudentPath.Stage.REGULAR),
        Session.SessionType.ADDITIONAL: (StudentPath.Status.LEARNING, StudentPath.Stage.ADDITIONAL),
        Session.SessionType.FOUNDATIONAL: (StudentPath.Status.LEARNING, StudentPath.Stage.FOUNDATIONAL),
        Session.SessionType.ACTIVITY: (StudentPath.Status.ACTIVITY_READY, StudentPath.Stage.ACTIVITY),
        Session.SessionType.POSTTEST: (StudentPath.Status.POSTTEST_READY, StudentPath.Stage.POSTTEST),
    }
    if session_type not in expected or (path.status, path.current_stage) != expected[session_type]:
        raise PermissionDenied("That assessment is not the student's current learning step.")
    if session_type in {
        Session.SessionType.REGULAR,
        Session.SessionType.ADDITIONAL,
        Session.SessionType.FOUNDATIONAL,
    } and path.current_lesson_id is None:
        raise ValidationError("A lesson assessment requires a current lesson.")


def _foundational_skill_ids(path: StudentPath) -> list:
    assigned = list(
        DecisionTargetSkill.objects.filter(
            decision__session__student=path.student,
            decision__session__lesson=path.current_lesson,
            target_kind=DecisionTargetSkill.TargetKind.NEXT_EXERCISE,
        )
        .order_by("decision__created_at", "skill__code")
        .values_list("skill_id", flat=True)
    )
    if assigned:
        return list(dict.fromkeys(assigned))
    return list(
        path.current_lesson.lesson_skills.order_by("display_order").values_list("skill_id", flat=True)
    )


def _question_items(path: StudentPath, session_type: str) -> list[QuestionSetItem]:
    set_type = (
        QuestionSet.SetType.PREPOST
        if session_type in {Session.SessionType.PRETEST, Session.SessionType.POSTTEST}
        else session_type
    )
    set_filter = {"is_published": True, "set_type": set_type}
    if session_type in {Session.SessionType.REGULAR, Session.SessionType.ADDITIONAL}:
        set_filter["lesson"] = path.current_lesson
    elif session_type == Session.SessionType.FOUNDATIONAL:
        skill_ids = _foundational_skill_ids(path)
        if not skill_ids:
            raise ValidationError("No foundational target skills are assigned.")
        question_sets = QuestionSet.objects.filter(
            is_published=True,
            set_type=QuestionSet.SetType.FOUNDATIONAL,
            skill_id__in=skill_ids,
        ).order_by("skill__code")
        if question_sets.count() != len(skill_ids):
            raise ValidationError("The foundational question sets are incomplete.")
        items = list(
            QuestionSetItem.objects.filter(question_set__in=question_sets)
            .select_related("question", "question_set__skill")
            .order_by("question_set__skill__code", "display_order")
        )
        distribution = Counter(item.question.skill_id for item in items)
        if len(items) not in {5, 10} or any(count != 5 for count in distribution.values()):
            raise ValidationError("Foundational issuance requires five items per target skill.")
        return items

    question_sets = QuestionSet.objects.filter(**set_filter)
    if question_sets.count() != 1:
        raise ValidationError("The requested published question set is misconfigured.")
    question_set = question_sets.get()
    items = list(
        question_set.items.select_related("question", "question__skill").order_by("display_order")
    )
    expected = EXPECTED_COUNTS[session_type]
    if len(items) != expected:
        raise ValidationError(f"{question_set.get_set_type_display()} issuance requires {expected} items.")
    if session_type in {Session.SessionType.REGULAR, Session.SessionType.ADDITIONAL}:
        distribution = Counter(item.question.skill_id for item in items)
        if sorted(distribution.values()) != [5, 5]:
            raise ValidationError("Lesson exercises require five questions per lesson skill.")
    return items


def _validate_materialized_questions(items: list[QuestionSetItem]) -> None:
    question_ids = [item.question_id for item in items]
    valid = (
        Question.objects.filter(pk__in=question_ids, is_published=True)
        .annotate(choice_count=Count("choices"))
        .filter(choice_count=4)
        .count()
    ) if items else 0
    if valid != len(items) or len(question_ids) != len(set(question_ids)):
        raise ValidationError("Issued questions must be unique, published, and have four choices.")


@transaction.atomic
def issue_session(*, student: User, session_type: str) -> Session:
    _require_access(student, session_type)
    path = StudentPath.objects.select_for_update().get(student=student)

    lesson = path.current_lesson if session_type in {
        Session.SessionType.REGULAR,
        Session.SessionType.ADDITIONAL,
        Session.SessionType.FOUNDATIONAL,
    } else None
    existing = (
        Session.objects.select_for_update()
        .filter(student=student, session_type=session_type, lesson=lesson, attempt_number=1)
        .first()
    )
    if existing is not None:
        if existing.status != Session.Status.COMPLETED:
            _validate_path(path, session_type)
        if existing.status == Session.Status.ISSUED:
            existing.status = Session.Status.IN_PROGRESS
            existing.started_at = timezone.now()
            existing.save(update_fields=["status", "started_at", "updated_at"])
        return existing

    _validate_path(path, session_type)
    source_items = _question_items(path, session_type)
    _validate_materialized_questions(source_items)
    now = timezone.now()
    session = Session.objects.create(
        student=student,
        session_type=session_type,
        lesson=lesson,
        status=Session.Status.IN_PROGRESS,
        attempt_number=1,
        started_at=now,
    )
    SessionItem.objects.bulk_create(
        [
            SessionItem(session=session, question=item.question, display_order=order)
            for order, item in enumerate(source_items, 1)
        ]
    )
    return session
