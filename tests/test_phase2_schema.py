from django.apps import apps
from django.db import models
from django.test import SimpleTestCase


EXPECTED_DOMAIN_TABLES = {
    "accounts_user",
    "classrooms_classroom",
    "classrooms_student_membership",
    "curriculum_skill",
    "curriculum_lesson",
    "curriculum_lesson_skill",
    "curriculum_video",
    "curriculum_question",
    "curriculum_question_choice",
    "curriculum_question_set",
    "curriculum_question_set_item",
    "learning_student_path",
    "learning_session",
    "learning_session_item",
    "learning_response",
    "adaptive_skill_mastery",
    "adaptive_mastery_event",
    "adaptive_decision",
    "adaptive_decision_target_skill",
    "feedback_session_feedback",
    "core_system_setting",
    "core_audit_event",
}


class DomainSchemaContractTests(SimpleTestCase):
    def test_exactly_the_22_documented_domain_models_exist(self):
        domain_apps = {"accounts", "classrooms", "curriculum", "learning", "adaptive", "feedback", "core"}
        tables = {
            model._meta.db_table
            for config in apps.get_app_configs()
            if config.label in domain_apps
            for model in config.get_models(include_auto_created=False)
        }
        self.assertEqual(tables, EXPECTED_DOMAIN_TABLES)

    def test_primary_key_contract(self):
        composite_tables = {
            "curriculum_lesson_skill",
            "curriculum_question_set_item",
            "adaptive_decision_target_skill",
        }
        exception_tables = composite_tables | {"learning_student_path", "core_system_setting"}
        for table in EXPECTED_DOMAIN_TABLES:
            model = next(model for model in apps.get_models() if model._meta.db_table == table)
            if table in composite_tables:
                self.assertIsInstance(model._meta.pk, models.CompositePrimaryKey)
            elif table not in exception_tables:
                self.assertIsInstance(model._meta.pk, models.UUIDField)

    def test_every_textchoices_field_has_a_database_check(self):
        for model in apps.get_models():
            if model._meta.db_table not in EXPECTED_DOMAIN_TABLES:
                continue
            for field in model._meta.fields:
                if not field.choices:
                    continue
                checks = [
                    constraint
                    for constraint in model._meta.constraints
                    if isinstance(constraint, models.CheckConstraint)
                ]
                self.assertTrue(
                    any(field.name in str(check.condition) for check in checks),
                    f"{model._meta.label}.{field.name} lacks a matching database CHECK",
                )
