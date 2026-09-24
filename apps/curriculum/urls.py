from django.urls import path

from . import views


app_name = "curriculum"

urlpatterns = [
    path("", views.content, name="content"),
    path("lessons/", views.view_lessons, name="lessons"),
    path("questions/", views.view_questions, name="questions"),
]
