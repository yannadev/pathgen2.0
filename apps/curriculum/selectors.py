from __future__ import annotations

from copy import deepcopy

from django.db.models import Prefetch

from .models import Lesson, LessonSkill, Question, QuestionChoice, QuestionSetItem, Skill, Video


VISIBLE_SET_TYPES = ("regular", "additional", "foundational", "activity")


def _youtube_embed_url(video_id: str, *, start: int | float | None = None, end: int | float | None = None) -> str:
    parameters = ["rel=0"]
    if start is not None:
        parameters.append(f"start={int(start)}")
    if end is not None:
        parameters.append(f"end={int(end)}")
    return f"https://www.youtube-nocookie.com/embed/{video_id}?{'&'.join(parameters)}"


def published_lesson_previews() -> list[Lesson]:
    lessons = list(
        Lesson.objects.filter(is_published=True)
        .prefetch_related(
            Prefetch(
                "lesson_skills",
                queryset=LessonSkill.objects.select_related("skill").order_by("display_order"),
            )
        )
        .order_by("lesson_order")
    )
    videos = {video.code: video for video in Video.objects.all()}
    for lesson in lessons:
        blocks = deepcopy(lesson.content_json)
        for block in blocks:
            if block.get("type") == "video" and block.get("video_code") in videos:
                video = videos[block["video_code"]]
                block["video"] = video
                block["embed_url"] = _youtube_embed_url(
                    video.youtube_video_id,
                    start=block.get("start_seconds"),
                    end=block.get("end_seconds"),
                )
        lesson.content_blocks = blocks
    return lessons


def published_content_questions(*, set_type: str = "", skill_code: str = "") -> list[Question]:
    visible_items = QuestionSetItem.objects.filter(
        question_set__is_published=True,
        question_set__set_type__in=VISIBLE_SET_TYPES,
    ).select_related("question_set", "question_set__lesson", "question_set__skill")
    queryset = (
        Question.objects.filter(
            is_published=True,
            set_items__question_set__is_published=True,
            set_items__question_set__set_type__in=VISIBLE_SET_TYPES,
        )
        .exclude(set_items__question_set__set_type="prepost")
        .select_related("skill", "video")
        .prefetch_related(
            Prefetch("choices", queryset=QuestionChoice.objects.order_by("display_order")),
            Prefetch("set_items", queryset=visible_items, to_attr="visible_set_items"),
        )
        .distinct()
        .order_by("code")
    )
    if set_type in VISIBLE_SET_TYPES:
        queryset = queryset.filter(set_items__question_set__set_type=set_type)
    if skill_code:
        queryset = queryset.filter(skill__code=skill_code)
    questions = list(queryset)
    for question in questions:
        question.content_sets = [item.question_set for item in question.visible_set_items]
        if question.video_id:
            question.embed_url = _youtube_embed_url(
                question.video.youtube_video_id,
                end=question.video_pause_seconds,
            )
    return questions


def published_content_counts() -> dict[str, int]:
    return {
        "lessons": Lesson.objects.filter(is_published=True).count(),
        "skills": Skill.objects.filter(lesson_skills__lesson__is_published=True).distinct().count(),
        "questions": Question.objects.filter(
            is_published=True,
            set_items__question_set__is_published=True,
            set_items__question_set__set_type__in=VISIBLE_SET_TYPES,
        ).distinct().count(),
    }
