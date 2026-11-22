import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_ok() -> None:
    response = APIClient().get(reverse("health"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.django_db
def test_schema_is_generated() -> None:
    response = APIClient().get(reverse("schema"))
    assert response.status_code == 200
    assert b"/api/v1/health/" in response.content
