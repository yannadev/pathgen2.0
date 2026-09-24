import json

from django.test import SimpleTestCase
from django.urls import reverse


class HealthEndpointTests(SimpleTestCase):
    def test_health_endpoint_is_a_dependency_free_no_store_liveness_check(self):
        response = self.client.get(reverse("core:health"))

        assert response.status_code == 200
        assert json.loads(response.content) == {"service": "pathgen", "status": "ok"}
        assert response.headers["Cache-Control"] == "no-store"

    def test_health_endpoint_rejects_mutating_methods(self):
        response = self.client.post(reverse("core:health"))

        assert response.status_code == 405
