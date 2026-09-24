from django.urls import path

from apps.classrooms import views


app_name = "teacher"

urlpatterns = [
    path("classes/", views.my_classes, name="my_classes"),
    path("classes/<uuid:classroom_id>/", views.class_detail, name="class_detail"),
]
