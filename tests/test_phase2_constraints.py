from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.adaptive.models import Decision, DecisionTargetSkill, MasteryEvent, SkillMastery
from apps.classrooms.models import Classroom
from apps.core.models import SystemSetting
from apps.curriculum.models import LessonSkill, Question, QuestionSet
from apps.feedback.models import SessionFeedback
from apps.learning.models import Response, Session, SessionItem
from tests.factories import (
    invalid_feedback_model,
    invalid_mastery_probability,
    invalid_membership_dates,
    invalid_question_set_scope,
    invalid_session_timestamps,
    invalid_text_question_media,
    make_audit_event,
    make_choice,
    make_classroom,
    make_completed_session,
    make_feedback,
    make_lesson,
    make_mastery,
    make_membership,
    make_question,
    make_session,
    make_skill,
    make_user,
    make_video,
)


class DirectDatabaseConstraintTests(TestCase):
    def assert_integrity_error(self, callback):
        with self.assertRaises(IntegrityError), transaction.atomic():
            callback()

    def test_textchoices_are_enforced_by_database_checks(self):
        user = make_user()
        self.assert_integrity_error(lambda: type(user).objects.filter(pk=user.pk).update(role="owner"))

        session = make_session(student=user)
        self.assert_integrity_error(
            lambda: Session.objects.filter(pk=session.pk).update(status="unknown")
        )

    def test_user_deactivation_state_is_atomic(self):
        user = make_user()
        self.assert_integrity_error(
            lambda: type(user).objects.filter(pk=user.pk).update(is_active=False)
        )

    def test_open_membership_is_unique_and_dates_are_ordered(self):
        classroom = make_classroom()
        student = make_user()
        admin = make_user(role="admin")
        make_membership(classroom=classroom, student=student, added_by=admin)
        self.assert_integrity_error(
            lambda: make_membership(classroom=classroom, student=student, added_by=admin)
        )
        self.assert_integrity_error(
            lambda: make_membership(**invalid_membership_dates(added_by=admin))
        )

    def test_probability_and_media_checks_reject_invalid_rows(self):
        self.assert_integrity_error(lambda: make_skill(p_l0=Decimal("1.0001")))
        self.assert_integrity_error(lambda: make_question(**invalid_text_question_media()))

    def test_video_cue_cannot_exceed_video_duration(self):
        video = make_video(duration_seconds=10)
        self.assert_integrity_error(
            lambda: make_question(
                presentation_type=Question.PresentationType.VIDEO,
                video=video,
                video_pause_seconds=Decimal("10.01"),
            )
        )

    def test_existing_video_cue_prevents_shortening_duration(self):
        video = make_video(duration_seconds=10)
        make_question(
            presentation_type=Question.PresentationType.VIDEO,
            video=video,
            video_pause_seconds=Decimal("9.00"),
        )
        self.assert_integrity_error(
            lambda: type(video).objects.filter(pk=video.pk).update(duration_seconds=8)
        )

    def test_question_set_scope_and_singleton_key_are_checked(self):
        self.assert_integrity_error(
            lambda: QuestionSet.objects.create(
                name="Invalid pre/post scope",
                **invalid_question_set_scope(),
            )
        )
        admin = make_user(role="admin")
        self.assert_integrity_error(
            lambda: SystemSetting.objects.create(
                singleton_key=2,
                study_access_enabled=True,
                posttest_access_enabled=False,
                changed_by=admin,
                changed_at=timezone.now(),
                revision=0,
            )
        )

    def test_classroom_archive_fields_are_all_or_none(self):
        classroom = make_classroom()
        self.assert_integrity_error(
            lambda: Classroom.objects.filter(pk=classroom.pk).update(status="archived")
        )

    def test_lesson_skill_orders_and_choice_key_are_unique(self):
        lesson = make_lesson()
        first = make_skill()
        second = make_skill()
        LessonSkill.objects.create(lesson=lesson, skill=first, display_order=1)
        self.assert_integrity_error(
            lambda: LessonSkill.objects.create(lesson=lesson, skill=second, display_order=1)
        )

        question = make_question(skill=first)
        make_choice(question=question, label="A", display_order=1, is_correct=True)
        self.assert_integrity_error(
            lambda: make_choice(question=question, label="B", display_order=2, is_correct=True)
        )

    def test_session_scope_timestamps_and_attempt_uniqueness(self):
        student = make_user()
        lesson = make_lesson()
        make_session(student=student, lesson=lesson)
        self.assert_integrity_error(lambda: make_session(student=student, lesson=lesson))
        self.assert_integrity_error(
            lambda: make_session(student=student, lesson=lesson, **invalid_session_timestamps())
        )
        self.assert_integrity_error(
            lambda: make_session(session_type=Session.SessionType.PRETEST, lesson=lesson)
        )

    def test_selected_choice_must_belong_to_issued_question(self):
        session = make_session()
        issued_question = make_question()
        other_question = make_question()
        wrong_choice = make_choice(question=other_question, is_correct=True)
        item = SessionItem.objects.create(session=session, question=issued_question, display_order=1)
        self.assert_integrity_error(
            lambda: Response.objects.create(
                session_item=item,
                selected_choice=wrong_choice,
                answered_at=timezone.now(),
            )
        )

    def test_posttest_response_cannot_create_mastery_event(self):
        student = make_user()
        skill = make_skill()
        question = make_question(skill=skill)
        choice = make_choice(question=question, is_correct=True)
        session = make_session(student=student, session_type=Session.SessionType.POSTTEST)
        item = SessionItem.objects.create(session=session, question=question, display_order=1)
        response = Response.objects.create(
            session_item=item,
            selected_choice=choice,
            answered_at=timezone.now(),
        )
        mastery = make_mastery(student=student, skill=skill)
        self.assert_integrity_error(
            lambda: MasteryEvent.objects.create(
                mastery=mastery,
                response=response,
                p_before=Decimal("0.2000"),
                p_after_observation=Decimal("0.4000"),
                p_after_learning=Decimal("0.4900"),
                learning_transition_applied=True,
            )
        )

    def test_decision_requires_eligible_session(self):
        pretest = make_completed_session(session_type=Session.SessionType.PRETEST)
        self.assert_integrity_error(
            lambda: Decision.objects.create(
                session=pretest,
                action=Decision.Action.PROGRESS,
                reason_code="invalid_scope",
                input_snapshot_json={},
                support_cutoff=Decimal("0.5000"),
            )
        )

    def test_decision_target_skill_must_belong_to_session_lesson(self):
        lesson = make_lesson()
        lesson_skill = make_skill()
        unrelated_skill = make_skill()
        LessonSkill.objects.create(lesson=lesson, skill=lesson_skill, display_order=1)
        decision = Decision.objects.create(
            session=make_completed_session(lesson=lesson),
            action=Decision.Action.PROGRESS,
            reason_code="synthetic_pass",
            input_snapshot_json={},
            support_cutoff=Decimal("0.5000"),
        )
        self.assert_integrity_error(
            lambda: DecisionTargetSkill.objects.create(
                decision=decision,
                skill=unrelated_skill,
                target_kind=DecisionTargetSkill.TargetKind.NEXT_EXERCISE,
            )
        )

    def test_mastery_probability_is_checked(self):
        self.assert_integrity_error(
            lambda: SkillMastery.objects.create(
                student=make_user(),
                skill=make_skill(),
                evidence_count=0,
                **invalid_mastery_probability(),
            )
        )

    def test_feedback_status_controls_model_name(self):
        self.assert_integrity_error(lambda: make_feedback(**invalid_feedback_model()))
        generated = make_feedback(
            generation_status=SessionFeedback.GenerationStatus.GENERATED,
            model_name="gpt-oss-120b",
        )
        self.assertEqual(generated.model_name, "gpt-oss-120b")

    def test_learning_history_protects_user_and_curriculum_deletion(self):
        student = make_user()
        lesson = make_lesson()
        make_session(student=student, lesson=lesson)
        with self.assertRaises(ProtectedError):
            student.delete()
        with self.assertRaises(ProtectedError):
            lesson.delete()

    def test_audit_actor_is_set_null_to_preserve_event(self):
        actor = make_user()
        event = make_audit_event(actor=actor)
        actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor_id)
