from __future__ import annotations

import uuid

from django.db import models
from django.db.models import Q


class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField()
    p_l0 = models.DecimalField(max_digits=5, decimal_places=4)
    p_t = models.DecimalField(max_digits=5, decimal_places=4)
    p_g = models.DecimalField(max_digits=5, decimal_places=4)
    p_s = models.DecimalField(max_digits=5, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "curriculum_skill"
        constraints = [
            models.CheckConstraint(condition=Q(p_l0__gte=0, p_l0__lte=1), name="skill_p_l0_valid"),
            models.CheckConstraint(condition=Q(p_t__gte=0, p_t__lte=1), name="skill_p_t_valid"),
            models.CheckConstraint(condition=Q(p_g__gte=0, p_g__lte=1), name="skill_p_g_valid"),
            models.CheckConstraint(condition=Q(p_s__gte=0, p_s__lte=1), name="skill_p_s_valid"),
        ]


class Lesson(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    slug = models.SlugField(max_length=128, unique=True)
    lesson_order = models.PositiveSmallIntegerField(unique=True)
    title = models.CharField(max_length=255)
    summary = models.TextField()
    content_json = models.JSONField(default=list)
    content_schema_version = models.PositiveSmallIntegerField()
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "curriculum_lesson"
        constraints = [
            models.CheckConstraint(condition=Q(lesson_order__gt=0), name="lesson_order_positive"),
            models.CheckConstraint(
                condition=Q(content_schema_version__gt=0),
                name="lesson_schema_version_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["is_published", "lesson_order"], name="lesson_published_order_idx"),
        ]


class LessonSkill(models.Model):
    pk = models.CompositePrimaryKey("lesson", "skill")
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="lesson_skills")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="lesson_skills")
    display_order = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "curriculum_lesson_skill"
        constraints = [
            models.UniqueConstraint(fields=["lesson", "skill"], name="lesson_skill_unique"),
            models.UniqueConstraint(fields=["lesson", "display_order"], name="lesson_skill_order_unique"),
            models.CheckConstraint(condition=Q(display_order__in=[1, 2]), name="lesson_skill_order_valid"),
        ]


class Video(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    youtube_video_id = models.CharField(max_length=32, unique=True)
    duration_seconds = models.PositiveIntegerField()
    transcript = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "curriculum_video"
        constraints = [
            models.CheckConstraint(condition=Q(duration_seconds__gt=0), name="video_duration_positive"),
            models.CheckConstraint(condition=~Q(transcript=""), name="video_transcript_nonblank"),
        ]


class Question(models.Model):
    class Difficulty(models.TextChoices):
        STANDARD = "standard", "Standard"
        FOUNDATIONAL = "foundational", "Foundational"

    class PresentationType(models.TextChoices):
        TEXT = "text", "Text"
        FIGURE = "figure", "Figure"
        VIDEO = "video", "Video"

    class CognitiveLevel(models.TextChoices):
        REMEMBER = "remember", "Remember"
        UNDERSTAND = "understand", "Understand"
        APPLY = "apply", "Apply"
        ANALYZE = "analyze", "Analyze"
        EVALUATE = "evaluate", "Evaluate"
        CREATE = "create", "Create"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="questions")
    prompt = models.TextField()
    difficulty = models.CharField(max_length=16, choices=Difficulty.choices)
    presentation_type = models.CharField(max_length=16, choices=PresentationType.choices)
    cognitive_level = models.CharField(max_length=16, choices=CognitiveLevel.choices)
    solution_steps_json = models.JSONField(default=list)
    explanation = models.TextField()
    hint = models.TextField(null=True, blank=True)
    feedback_correct = models.TextField()
    feedback_incorrect = models.TextField()
    image_asset = models.CharField(max_length=255, null=True, blank=True)
    image_alt = models.TextField(null=True, blank=True)
    visual_component = models.CharField(max_length=128, null=True, blank=True)
    visual_config_json = models.JSONField(null=True, blank=True)
    video = models.ForeignKey(
        Video,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="questions",
    )
    video_pause_seconds = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "curriculum_question"
        constraints = [
            models.CheckConstraint(
                condition=Q(difficulty__in=["standard", "foundational"]),
                name="question_difficulty_valid",
            ),
            models.CheckConstraint(
                condition=Q(presentation_type__in=["text", "figure", "video"]),
                name="question_presentation_valid",
            ),
            models.CheckConstraint(
                condition=Q(
                    cognitive_level__in=[
                        "remember",
                        "understand",
                        "apply",
                        "analyze",
                        "evaluate",
                        "create",
                    ]
                ),
                name="question_cognitive_valid",
            ),
            models.CheckConstraint(
                condition=Q(difficulty="foundational") | Q(hint__isnull=True),
                name="question_hint_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        presentation_type="text",
                        image_asset__isnull=True,
                        image_alt__isnull=True,
                        visual_component__isnull=True,
                        visual_config_json__isnull=True,
                        video__isnull=True,
                        video_pause_seconds__isnull=True,
                    )
                    | (
                        Q(
                            presentation_type="figure",
                            image_alt__isnull=False,
                            video__isnull=True,
                            video_pause_seconds__isnull=True,
                        )
                        & ~Q(image_alt="")
                        & (
                            Q(
                                image_asset__isnull=False,
                                visual_component__isnull=True,
                                visual_config_json__isnull=True,
                            )
                            & ~Q(image_asset="")
                            | Q(
                                image_asset__isnull=True,
                                visual_component__isnull=False,
                                visual_config_json__isnull=False,
                            )
                            & ~Q(visual_component="")
                        )
                    )
                    | (
                        Q(
                            presentation_type="video",
                            image_asset__isnull=True,
                            image_alt__isnull=True,
                            visual_component__isnull=True,
                            visual_config_json__isnull=True,
                            video__isnull=False,
                            video_pause_seconds__isnull=False,
                        )
                        & Q(video_pause_seconds__gt=0)
                    )
                ),
                name="question_media_shape_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["skill", "is_published"], name="question_skill_published_idx"),
            models.Index(
                fields=["presentation_type", "is_published"],
                name="question_media_published_idx",
            ),
            models.Index(fields=["difficulty"], name="question_difficulty_idx"),
        ]


class QuestionChoice(models.Model):
    class Label(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    label = models.CharField(max_length=1, choices=Label.choices)
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    misconception_code = models.CharField(max_length=64, null=True, blank=True)
    display_order = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "curriculum_question_choice"
        constraints = [
            models.CheckConstraint(condition=Q(label__in=["A", "B", "C", "D"]), name="choice_label_valid"),
            models.CheckConstraint(condition=Q(display_order__range=(1, 4)), name="choice_order_valid"),
            models.UniqueConstraint(fields=["question", "label"], name="choice_question_label_unique"),
            models.UniqueConstraint(fields=["question", "display_order"], name="choice_question_order_unique"),
            models.UniqueConstraint(
                fields=["question"],
                condition=Q(is_correct=True),
                name="choice_one_correct",
            ),
        ]


class QuestionSet(models.Model):
    class SetType(models.TextChoices):
        PREPOST = "prepost", "Pre/post"
        REGULAR = "regular", "Regular"
        ADDITIONAL = "additional", "Additional"
        FOUNDATIONAL = "foundational", "Foundational"
        ACTIVITY = "activity", "Activity"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    set_type = models.CharField(max_length=16, choices=SetType.choices)
    lesson = models.ForeignKey(
        Lesson,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="question_sets",
    )
    skill = models.ForeignKey(
        Skill,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="question_sets",
    )
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "curriculum_question_set"
        constraints = [
            models.CheckConstraint(
                condition=Q(set_type__in=["prepost", "regular", "additional", "foundational", "activity"]),
                name="question_set_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(set_type__in=["regular", "additional"], lesson__isnull=False, skill__isnull=True)
                    | Q(set_type="foundational", lesson__isnull=True, skill__isnull=False)
                    | Q(set_type__in=["prepost", "activity"], lesson__isnull=True, skill__isnull=True)
                ),
                name="question_set_scope_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["set_type", "is_published"], name="qset_type_published_idx"),
            models.Index(fields=["lesson"], name="qset_lesson_idx"),
            models.Index(fields=["skill"], name="qset_skill_idx"),
        ]


class QuestionSetItem(models.Model):
    pk = models.CompositePrimaryKey("question_set", "question")
    question_set = models.ForeignKey(
        QuestionSet,
        on_delete=models.CASCADE,
        related_name="items",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.PROTECT,
        related_name="set_items",
    )
    display_order = models.PositiveSmallIntegerField()

    class Meta:
        db_table = "curriculum_question_set_item"
        constraints = [
            models.UniqueConstraint(fields=["question_set", "question"], name="qset_item_question_unique"),
            models.UniqueConstraint(fields=["question_set", "display_order"], name="qset_item_order_unique"),
            models.CheckConstraint(condition=Q(display_order__gt=0), name="qset_item_order_positive"),
        ]
