from __future__ import annotations

from collections import Counter
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

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
from apps.curriculum.seed import HOTS, LOTS, load_and_validate_seed_package
from tests.factories import make_user


class CurriculumValidationCommandTests(TestCase):
    def test_approved_json_schemas_counts_rules_and_pdf_hash_validate(self):
        package = load_and_validate_seed_package()
        self.assertEqual(len(package.lessons), 3)
        self.assertEqual(len(package.questions), 135)
        self.assertEqual(len(package.question_sets), 14)
        self.assertEqual(len(package.prepost["source_sha256"]), 64)

        output = StringIO()
        call_command("validate_curriculum", stdout=output)
        self.assertIn("Curriculum validation passed", output.getvalue())
        self.assertIn("Protected PDF SHA-256 verified", output.getvalue())


class CurriculumSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_curriculum", verbosity=0)

    def test_seed_imports_exact_counts_and_is_idempotent(self):
        self.assertEqual(Lesson.objects.count(), 3)
        self.assertEqual(Skill.objects.count(), 6)
        self.assertEqual(Question.objects.count(), 135)
        self.assertEqual(QuestionChoice.objects.count(), 540)
        self.assertEqual(QuestionSet.objects.count(), 14)
        self.assertEqual(QuestionSetItem.objects.count(), 135)
        self.assertEqual(Video.objects.count(), 4)
        self.assertEqual(LessonSkill.objects.count(), 6)

        call_command("seed_curriculum", verbosity=0)
        self.assertEqual(Question.objects.count(), 135)
        self.assertEqual(QuestionChoice.objects.count(), 540)

    def test_choices_set_counts_and_distributions_match_contract(self):
        for question in Question.objects.prefetch_related("choices"):
            choices = list(question.choices.order_by("display_order"))
            self.assertEqual([choice.label for choice in choices], list("ABCD"))
            self.assertEqual(len({choice.text for choice in choices}), 4)
            self.assertEqual(sum(choice.is_correct for choice in choices), 1)

        counts = Counter()
        for question_set in QuestionSet.objects.prefetch_related("items__question"):
            items = list(question_set.items.order_by("display_order"))
            counts[question_set.set_type] += len(items)
            levels = [item.question.cognitive_level for item in items]
            if question_set.set_type in {"regular", "additional"}:
                self.assertEqual((sum(level in LOTS for level in levels), sum(level in HOTS for level in levels)), (6, 4))
        self.assertEqual(
            counts,
            Counter({"prepost": 30, "regular": 30, "additional": 30, "foundational": 30, "activity": 15}),
        )

        activity = QuestionSet.objects.get(set_type="activity")
        activity_questions = [item.question for item in activity.items.select_related("question__skill")]
        self.assertEqual(Counter(question.skill.code for question in activity_questions), Counter({"S1": 3, "S2": 2, "S3": 3, "S4": 3, "S5": 2, "S6": 2}))
        self.assertEqual(
            (sum(question.cognitive_level in LOTS for question in activity_questions), sum(question.cognitive_level in HOTS for question in activity_questions)),
            (9, 6),
        )

    def test_published_curriculum_is_immutable(self):
        lesson = Lesson.objects.get(code="L1")
        lesson.title = "Changed after publication"
        with self.assertRaises(ValidationError):
            lesson.save()

        question = Question.objects.get(code="L1-R-S1-01")
        question.prompt = "Changed after publication"
        with self.assertRaises(ValidationError):
            question.save()


class CurriculumContentViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_curriculum", verbosity=0)
        cls.admin = make_user(role="admin", username="phase5-admin")
        cls.teacher = make_user(role="teacher", username="phase5-teacher")
        cls.student = make_user(role="student", username="phase5-student")

    def test_admin_and_teacher_can_open_three_read_only_pages(self):
        for user in (self.admin, self.teacher):
            self.client.force_login(user)
            for route in ("curriculum:content", "curriculum:lessons", "curriculum:questions"):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200, route)
                self.assertContains(response, 'meta name="color-scheme" content="only light"')

    def test_student_is_denied_and_protected_set_is_excluded(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("curriculum:content")).status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("curriculum:questions"))
        self.assertEqual(response.context["questions"].__len__(), 105)
        self.assertNotContains(response, "PP-01")
        self.assertNotContains(response, "Which of the following is an integer?")

    def test_filters_and_youtube_ids_generate_privacy_enhanced_embeds(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("curriculum:questions"), {"type": "activity", "skill": "S2"})
        self.assertEqual(len(response.context["questions"]), 2)
        self.assertContains(response, "youtube-nocookie.com/embed/NQSN00zL5gg")
        self.assertNotContains(response, "youtube.com/watch")

        lesson_response = self.client.get(reverse("curriculum:lessons"))
        self.assertContains(lesson_response, "youtube-nocookie.com/embed/qW-Ce44ll0Q")
        self.assertContains(lesson_response, "Read transcript")
