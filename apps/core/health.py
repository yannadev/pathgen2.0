"""Dependency-free liveness endpoint."""

from django.http import JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    response = JsonResponse({"service": "pathgen", "status": "ok"})
    response.headers["Cache-Control"] = "no-store"
    return response
