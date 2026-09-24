from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.accounts.models import User
from apps.accounts.permissions import role_required

from .models import QuestionSet, Skill
from .selectors import (
    VISIBLE_SET_TYPES,
    published_content_counts,
    published_content_questions,
    published_lesson_previews,
)


content_reader_required = role_required(User.Role.ADMIN, User.Role.TEACHER)


@never_cache
@content_reader_required
@require_safe
def content(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "shared/content.html",
        {"counts": published_content_counts(), "breadcrumbs": [("", "Content")]},
    )


@never_cache
@content_reader_required
@require_safe
def view_lessons(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "shared/view_lessons.html",
        {
            "lessons": published_lesson_previews(),
            "breadcrumbs": [(reverse("curriculum:content"), "Content"), ("", "Lessons")],
        },
    )


@never_cache
@content_reader_required
@require_safe
def view_questions(request: HttpRequest) -> HttpResponse:
    selected_type = request.GET.get("type", "").strip()
    selected_skill = request.GET.get("skill", "").strip()
    if selected_type not in VISIBLE_SET_TYPES:
        selected_type = ""
    if selected_skill and not Skill.objects.filter(code=selected_skill).exists():
        selected_skill = ""
    type_labels = dict(QuestionSet.SetType.choices)
    return render(
        request,
        "shared/view_questions.html",
        {
            "questions": published_content_questions(
                set_type=selected_type,
                skill_code=selected_skill,
            ),
            "skills": Skill.objects.filter(
                lesson_skills__lesson__is_published=True
            ).distinct().order_by("code"),
            "set_types": [(value, type_labels[value]) for value in VISIBLE_SET_TYPES],
            "selected_type": selected_type,
            "selected_skill": selected_skill,
            "breadcrumbs": [(reverse("curriculum:content"), "Content"), ("", "Questions")],
        },
    )
