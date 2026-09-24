from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from itertools import count
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.adaptive.models import Decision, DecisionTargetSkill, MasteryEvent, SkillMastery
from apps.classrooms.models import Classroom, StudentMembership
from apps.core.models import AuditEvent, SystemSetting
from apps.curriculum.models import (
    Lesson,
    LessonSkill,
    Question,
    QuestionChoice,
    QuestionSet,
    QuestionSetItem,
    Skill,
    Video,
)
from apps.feedback.models import SessionFeedback
from apps.learning.models import Response, Session, SessionItem, StudentPath


def token() -> str:
    return uuid4().hex[:12]


_lesson_orders = count(1)
_UNSET = object()


def make_user(*, role="student", username=None, **overrides):
    values = {"username": username or f"{role}-{token()}", "role": role, **overrides}
    return get_user_model().objects.create_user(**values)


def make_skill(**overrides):
    suffix = token()
    values = {
        "code": f"skill-{suffix}",
        "name": f"Skill {suffix}",
        "description": "Synthetic test skill.",
        "p_l0": Decimal("0.2000"),
        "p_t": Decimal("0.1500"),
        "p_g": Decimal("0.2000"),
        "p_s": Decimal("0.1000"),
        **overrides,
    }
    return Skill.objects.create(**values)


def make_lesson(**overrides):
    suffix = token()
    values = {
        "code": f"lesson-{suffix}",
        "slug": f"lesson-{suffix}",
        "lesson_order": next(_lesson_orders),
        "title": f"Lesson {suffix}",
        "summary": "Synthetic test lesson.",
        "content_json": [],
        "content_schema_version": 1,
        **overrides,
    }
    return Lesson.objects.create(**values)


def make_lesson_skill(*, lesson=None, skill=None, display_order=1):
    return LessonSkill.objects.create(
        lesson=lesson or make_lesson(),
        skill=skill or make_skill(),
        display_order=display_order,
    )


def make_question(*, skill=None, **overrides):
    suffix = token()
    values = {
        "code": f"question-{suffix}",
        "skill": skill or make_skill(),
        "prompt": "What is the answer?",
        "difficulty": Question.Difficulty.STANDARD,
        "presentation_type": Question.PresentationType.TEXT,
        "cognitive_level": Question.CognitiveLevel.APPLY,
        "solution_steps_json": ["Solve the synthetic item."],
        "explanation": "Synthetic explanation.",
        "feedback_correct": "Correct.",
        "feedback_incorrect": "Try again.",
        **overrides,
    }
    return Question.objects.create(**values)


def make_choice(*, question, label="A", display_order=1, is_correct=False, **overrides):
    return QuestionChoice.objects.create(
        question=question,
        label=label,
        text=overrides.pop("text", f"Choice {label}"),
        display_order=display_order,
        is_correct=is_correct,
        **overrides,
    )


def make_video(**overrides):
    suffix = token()
    values = {
        "code": f"video-{suffix}",
        "title": f"Video {suffix}",
        "youtube_video_id": suffix,
        "duration_seconds": 120,
        "transcript": "Reviewed synthetic transcript.",
        **overrides,
    }
    return Video.objects.create(**values)


def make_question_set(*, lesson=_UNSET, skill=None, set_type=QuestionSet.SetType.REGULAR, **overrides):
    if lesson is _UNSET:
        if set_type in {QuestionSet.SetType.REGULAR, QuestionSet.SetType.ADDITIONAL}:
            lesson = make_lesson()
        else:
            lesson = None
    values = {
        "name": f"Question set {token()}",
        "set_type": set_type,
        "lesson": lesson,
        "skill": skill,
        **overrides,
    }
    return QuestionSet.objects.create(**values)


def make_question_set_item(*, question_set=None, question=None, display_order=1):
    return QuestionSetItem.objects.create(
        question_set=question_set or make_question_set(),
        question=question or make_question(),
        display_order=display_order,
    )


def make_classroom(*, teacher=None, **overrides):
    suffix = token()
    values = {
        "code": f"class-{suffix}",
        "name": f"Class {suffix}",
        "teacher": teacher,
        **overrides,
    }
    return Classroom.objects.create(**values)


def make_membership(*, classroom=None, student=None, added_by=None, **overrides):
    values = {
        "classroom": classroom or make_classroom(),
        "student": student or make_user(role="student"),
        "joined_at": timezone.now(),
        "added_by": added_by or make_user(role="admin"),
        **overrides,
    }
    return StudentMembership.objects.create(**values)


def make_path(*, student=None, **overrides):
    values = {
        "student": student or make_user(role="student"),
        "status": StudentPath.Status.PRETEST_REQUIRED,
        "current_stage": StudentPath.Stage.PRETEST,
        **overrides,
    }
    return StudentPath.objects.create(**values)


def make_session(*, student=None, lesson=_UNSET, session_type=Session.SessionType.REGULAR, **overrides):
    if lesson is _UNSET:
        if session_type in {
            Session.SessionType.REGULAR,
            Session.SessionType.ADDITIONAL,
            Session.SessionType.FOUNDATIONAL,
        }:
            lesson = make_lesson()
        else:
            lesson = None
    values = {
        "student": student or make_user(role="student"),
        "session_type": session_type,
        "lesson": lesson,
        "status": Session.Status.ISSUED,
        "attempt_number": 1,
        **overrides,
    }
    return Session.objects.create(**values)


def make_completed_session(**overrides):
    now = timezone.now()
    return make_session(
        status=Session.Status.COMPLETED,
        started_at=now - timedelta(minutes=10),
        submitted_at=now - timedelta(minutes=1),
        completed_at=now,
        **overrides,
    )


def make_response(*, session=None, question=None, choice=None, **overrides):
    question = question or make_question()
    choice = choice or make_choice(question=question, is_correct=True)
    session = session or make_session()
    item = SessionItem.objects.create(session=session, question=question, display_order=1)
    return Response.objects.create(
        session_item=item,
        selected_choice=choice,
        answered_at=timezone.now(),
        **overrides,
    )


def make_session_item(*, session=None, question=None, display_order=1):
    return SessionItem.objects.create(
        session=session or make_session(),
        question=question or make_question(),
        display_order=display_order,
    )


def make_mastery(*, student=None, skill=None, **overrides):
    values = {
        "student": student or make_user(role="student"),
        "skill": skill or make_skill(),
        "p_known": Decimal("0.2000"),
        "evidence_count": 0,
        **overrides,
    }
    return SkillMastery.objects.create(**values)


def make_mastery_event(*, mastery, response, **overrides):
    values = {
        "mastery": mastery,
        "response": response,
        "p_before": Decimal("0.2000"),
        "p_after_observation": Decimal("0.5000"),
        "p_after_learning": Decimal("0.5750"),
        "learning_transition_applied": True,
        **overrides,
    }
    return MasteryEvent.objects.create(**values)


def make_decision(*, session=None, **overrides):
    values = {
        "session": session or make_completed_session(),
        "action": Decision.Action.PROGRESS,
        "reason_code": "synthetic_pass",
        "input_snapshot_json": {},
        "support_cutoff": Decimal("0.5000"),
        **overrides,
    }
    return Decision.objects.create(**values)


def make_decision_target(*, decision, skill, target_kind=DecisionTargetSkill.TargetKind.NEXT_EXERCISE):
    return DecisionTargetSkill.objects.create(
        decision=decision,
        skill=skill,
        target_kind=target_kind,
    )


def make_feedback(*, session=None, **overrides):
    values = {
        "session": session or make_completed_session(),
        "feedback_text": "Synthetic deterministic feedback.",
        "generation_status": SessionFeedback.GenerationStatus.FALLBACK,
        "model_name": None,
        **overrides,
    }
    return SessionFeedback.objects.create(**values)


def make_system_setting(*, changed_by=None, **overrides):
    values = {
        "changed_by": changed_by or make_user(role="admin"),
        "changed_at": timezone.now(),
        **overrides,
    }
    setting, _ = SystemSetting.objects.update_or_create(
        singleton_key=1,
        defaults=values,
    )
    return setting


def make_audit_event(*, actor=None, **overrides):
    values = {
        "actor": actor,
        "action": "synthetic.created",
        "target_type": "synthetic",
        "target_id": uuid4(),
        "target_snapshot_json": {},
        "metadata_json": {},
        **overrides,
    }
    return AuditEvent.objects.create(**values)


def invalid_membership_dates(**overrides):
    joined_at = timezone.now()
    return {"joined_at": joined_at, "left_at": joined_at - timedelta(seconds=1), **overrides}


def invalid_text_question_media(**overrides):
    return {"presentation_type": Question.PresentationType.TEXT, "image_asset": "unexpected.svg", **overrides}


def invalid_session_timestamps(**overrides):
    return {"status": Session.Status.COMPLETED, "started_at": None, "submitted_at": None, "completed_at": None, **overrides}


def invalid_feedback_model(**overrides):
    return {
        "generation_status": SessionFeedback.GenerationStatus.FALLBACK,
        "model_name": "gpt-oss-120b",
        **overrides,
    }


def invalid_question_set_scope(**overrides):
    return {"set_type": QuestionSet.SetType.PREPOST, "lesson": make_lesson(), **overrides}


def invalid_mastery_probability(**overrides):
    return {"p_known": Decimal("1.0001"), **overrides}
