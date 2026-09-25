from django.urls import path

from . import views


app_name = "learning"

urlpatterns = [
    path("", views.my_lesson, name="my_lesson"),
    path("lessons/<slug:lesson_slug>/", views.lesson_detail, name="lesson"),
    path("lessons/<slug:lesson_slug>/complete/", views.lesson_complete, name="lesson_complete"),
    path("assessment/<str:session_type>/", views.assessment_overview, name="assessment_overview"),
    path("assessment/<str:session_type>/start/", views.assessment_start, name="assessment_start"),
    path(
        "assessment/sessions/<uuid:session_id>/questions/<int:order>/",
        views.assessment_question,
        name="assessment_question",
    ),
    path(
        "assessment/sessions/<uuid:session_id>/items/<uuid:item_id>/answer/",
        views.assessment_answer,
        name="assessment_answer",
    ),
    path(
        "assessment/sessions/<uuid:session_id>/items/<uuid:item_id>/hint/",
        views.assessment_hint,
        name="assessment_hint",
    ),
    path(
        "assessment/sessions/<uuid:session_id>/result/",
        views.assessment_result,
        name="assessment_result",
    ),
]
