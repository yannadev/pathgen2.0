from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.adaptive.models import MasteryEvent
from apps.curriculum.models import Lesson, Question, QuestionChoice
from apps.learning.models import Response, Session, SessionItem, StudentPath
from apps.learning.services import complete_lesson_content, issue_session, submit_response
from tests.factories import make_path, make_system_setting, make_user


class Phase6Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_curriculum", verbosity=0)
        cls.admin = make_user(role="admin", username="phase6-admin")
        cls.teacher = make_user(role="teacher", username="phase6-teacher")
        make_system_setting(
            changed_by=cls.admin,
            study_access_enabled=True,
            posttest_access_enabled=True,
        )

    def make_student_path(self, **path_values):
        student = make_user(role="student")
        return student, make_path(student=student, **path_values)

    def test_pretest_issuance_is_materialized_and_idempotent(self):
        student, _path = self.make_student_path()

        first = issue_session(student=student, session_type=Session.SessionType.PRETEST)
        second = issue_session(student=student, session_type=Session.SessionType.PRETEST)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, Session.Status.IN_PROGRESS)
        self.assertEqual(first.items.count(), 30)
        self.assertEqual(
            list(first.items.order_by("display_order").values_list("display_order", flat=True)),
            list(range(1, 31)),
        )

    def test_submission_validates_choice_order_and_is_idempotent(self):
        student, _path = self.make_student_path()
        session = issue_session(student=student, session_type=Session.SessionType.PRETEST)
        first, second = list(session.items.order_by("display_order")[:2])
        wrong_question_choice = second.question.choices.first()

        with self.assertRaises(ValidationError):
            submit_response(
                student=student,
                session_id=session.pk,
                item_id=first.pk,
                choice_id=wrong_question_choice.pk,
            )

        first_choice = first.question.choices.order_by("display_order").first()
        alternate_choice = first.question.choices.order_by("display_order")[1]
        with patch("apps.learning.interfaces.record_response_evidence") as evidence:
            saved = submit_response(
                student=student,
                session_id=session.pk,
                item_id=first.pk,
                choice_id=first_choice.pk,
            )
            duplicate = submit_response(
                student=student,
                session_id=session.pk,
                item_id=first.pk,
                choice_id=alternate_choice.pk,
            )

        self.assertFalse(saved.duplicate)
        self.assertTrue(duplicate.duplicate)
        self.assertIsNone(saved.is_correct)
        self.assertEqual(duplicate.response.selected_choice_id, first_choice.pk)
        self.assertEqual(Response.objects.filter(session_item=first).count(), 1)
        evidence.assert_called_once_with(response=saved.response)

        with self.assertRaises(ValidationError):
            submit_response(
                student=student,
                session_id=session.pk,
                item_id=second.pk,
                choice_id=first_choice.pk,
            )

    def test_foundational_hint_is_server_trusted_and_feedback_is_immediate(self):
        lesson = Lesson.objects.get(lesson_order=1)
        student, _path = self.make_student_path(
            status=StudentPath.Status.LEARNING,
            current_lesson=lesson,
            current_stage=StudentPath.Stage.FOUNDATIONAL,
        )
        session = issue_session(student=student, session_type=Session.SessionType.FOUNDATIONAL)
        item = session.items.order_by("display_order").first()
        choice = item.question.choices.order_by("display_order").first()

        outcome = submit_response(
            student=student,
            session_id=session.pk,
            item_id=item.pk,
            choice_id=choice.pk,
            hint_was_revealed=True,
        )

        self.assertEqual(session.items.count(), 10)
        self.assertTrue(outcome.response.hint_used)
        self.assertTrue(outcome.reveal_feedback)
        self.assertIsInstance(outcome.is_correct, bool)

    def test_fixed_path_transitions_and_posttest_creates_no_bkt_event(self):
        first_lesson = Lesson.objects.get(lesson_order=1)
        student, path = self.make_student_path()
        pretest = self._one_item_session(student, Session.SessionType.PRETEST)

        self._complete_one_item_session(student, pretest)
        path.refresh_from_db()
        self.assertEqual(
            (path.status, path.current_stage, path.current_lesson_id),
            (StudentPath.Status.LEARNING, StudentPath.Stage.LESSON, first_lesson.pk),
        )

        post_student, post_path = self.make_student_path(
            status=StudentPath.Status.POSTTEST_READY,
            current_stage=StudentPath.Stage.POSTTEST,
        )
        posttest = self._one_item_session(post_student, Session.SessionType.POSTTEST)
        with patch("apps.learning.interfaces.record_response_evidence") as evidence:
            self._complete_one_item_session(post_student, posttest)

        evidence.assert_not_called()
        self.assertEqual(MasteryEvent.objects.filter(response__session_item__session=posttest).count(), 0)
        post_path.refresh_from_db()
        self.assertEqual(post_path.status, StudentPath.Status.COMPLETED)

    def test_activity_completion_advances_to_posttest(self):
        student, path = self.make_student_path(
            status=StudentPath.Status.ACTIVITY_READY,
            current_stage=StudentPath.Stage.ACTIVITY,
        )
        activity = self._one_item_session(student, Session.SessionType.ACTIVITY)

        outcome = self._complete_one_item_session(student, activity)

        self.assertIsInstance(outcome.is_correct, bool)
        path.refresh_from_db()
        self.assertEqual(
            (path.status, path.current_stage),
            (StudentPath.Status.POSTTEST_READY, StudentPath.Stage.POSTTEST),
        )

    def test_lesson_and_assessment_views_are_student_owned(self):
        lesson = Lesson.objects.get(lesson_order=1)
        student, path = self.make_student_path(
            status=StudentPath.Status.LEARNING,
            current_lesson=lesson,
            current_stage=StudentPath.Stage.LESSON,
        )
        self.client.force_login(student)

        self.assertEqual(self.client.get(reverse("learning:my_lesson")).status_code, 200)
        lesson_response = self.client.get(reverse("learning:lesson", args=[lesson.slug]))
        self.assertEqual(lesson_response.status_code, 200)
        self.assertTemplateUsed(lesson_response, "student/lesson.html")
        complete = self.client.post(reverse("learning:lesson_complete", args=[lesson.slug]))
        self.assertEqual(complete.status_code, 302)
        path.refresh_from_db()
        self.assertEqual(path.current_stage, StudentPath.Stage.REGULAR)

        other_student, _other_path = self.make_student_path()
        other_session = issue_session(student=other_student, session_type=Session.SessionType.PRETEST)
        self.assertEqual(
            self.client.get(
                reverse("learning:assessment_question", args=[other_session.pk, 1])
            ).status_code,
            404,
        )

        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse("learning:my_lesson")).status_code, 403)

    def test_pretest_ui_keeps_correctness_hidden_until_completion(self):
        student, _path = self.make_student_path()
        self.client.force_login(student)
        start = self.client.post(
            reverse("learning:assessment_start", args=[Session.SessionType.PRETEST])
        )
        session = Session.objects.get(student=student, session_type=Session.SessionType.PRETEST)
        item = session.items.order_by("display_order").first()
        choice = item.question.choices.order_by("display_order").first()

        self.assertRedirects(
            start,
            reverse("learning:assessment_question", args=[session.pk, 1]),
            fetch_redirect_response=False,
        )
        answer = self.client.post(
            reverse("learning:assessment_answer", args=[session.pk, item.pk]),
            {"choice": choice.pk},
            follow=True,
        )
        self.assertContains(answer, "Correctness and the explanation remain hidden")
        self.assertNotContains(answer, ">Correct<")
        self.assertNotContains(answer, ">Incorrect<")

    def test_activity_ui_exposes_video_cue_and_transcript(self):
        student, _path = self.make_student_path(
            status=StudentPath.Status.ACTIVITY_READY,
            current_stage=StudentPath.Stage.ACTIVITY,
        )
        session = issue_session(student=student, session_type=Session.SessionType.ACTIVITY)
        video_item = session.items.filter(question__presentation_type=Question.PresentationType.VIDEO).first()
        for item in session.items.filter(display_order__lt=video_item.display_order).order_by("display_order"):
            submit_response(
                student=student,
                session_id=session.pk,
                item_id=item.pk,
                choice_id=item.question.choices.order_by("display_order").first().pk,
            )
        self.client.force_login(student)

        response = self.client.get(
            reverse("learning:assessment_question", args=[session.pk, video_item.display_order])
        )

        self.assertContains(response, "data-video-question")
        self.assertContains(response, f'data-video-cue="{video_item.question.video_pause_seconds}"')
        self.assertContains(response, "youtube-nocookie.com")
        self.assertContains(response, "YouTube transcript")
        self.assertContains(response, f"Video ID: {video_item.question.video.youtube_video_id}")

    def test_result_reveals_explanation_only_after_completed_session(self):
        student, _path = self.make_student_path(
            status=StudentPath.Status.COMPLETED,
            current_stage=StudentPath.Stage.POSTTEST,
        )
        session = self._one_item_session(student, Session.SessionType.POSTTEST)
        item = session.items.get()
        choice = item.question.choices.get(is_correct=True)
        response = Response.objects.create(
            session_item=item,
            selected_choice=choice,
            answered_at=timezone.now(),
        )
        now = timezone.now()
        session.status = Session.Status.COMPLETED
        session.submitted_at = now
        session.completed_at = now
        session.save(update_fields=["status", "submitted_at", "completed_at", "updated_at"])
        self.client.force_login(student)

        result = self.client.get(reverse("learning:assessment_result", args=[session.pk]))

        self.assertContains(result, "Assessment complete")
        self.assertContains(result, response.session_item.question.explanation)
        self.assertContains(result, "Correct")

    def _one_item_session(self, student, session_type):
        question = Question.objects.filter(
            set_items__question_set__set_type="prepost",
            is_published=True,
        ).first()
        session = Session.objects.create(
            student=student,
            session_type=session_type,
            status=Session.Status.IN_PROGRESS,
            started_at=timezone.now(),
        )
        SessionItem.objects.create(session=session, question=question, display_order=1)
        return session

    def _complete_one_item_session(self, student, session):
        item = session.items.select_related("question").get()
        choice = QuestionChoice.objects.filter(question=item.question).order_by("display_order").first()
        return submit_response(
            student=student,
            session_id=session.pk,
            item_id=item.pk,
            choice_id=choice.pk,
        )


class Phase6ResponseLockTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_curriculum", verbosity=0)
        cls.admin = make_user(role="admin", username="phase6-lock-admin")
        make_system_setting(changed_by=cls.admin, study_access_enabled=True)

    def test_saved_response_cannot_be_changed_or_deleted(self):
        student = make_user(role="student")
        make_path(student=student)
        session = issue_session(student=student, session_type=Session.SessionType.PRETEST)
        item = session.items.order_by("display_order").first()
        choices = list(item.question.choices.order_by("display_order")[:2])
        response = submit_response(
            student=student,
            session_id=session.pk,
            item_id=item.pk,
            choice_id=choices[0].pk,
        ).response

        response.selected_choice = choices[1]
        with self.assertRaises(ValidationError):
            response.save()
        with self.assertRaises(ValidationError):
            response.delete()
