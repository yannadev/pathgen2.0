from django.urls import path

from .health import health


app_name = "core"

urlpatterns = [
    path("health/", health, name="health"),
]
