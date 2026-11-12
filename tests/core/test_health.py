"""Pruebas del endpoint GET /health/ (SPEC 01, §3.3)."""

from unittest import mock

import pytest
from django.db import OperationalError
from django.urls import reverse

URL = reverse("core:health")


@pytest.mark.django_db
def test_health_ok_when_database_responds(client):
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_fails(client):
    with mock.patch(
        "apps.core.views.connection.cursor",
        side_effect=OperationalError("connection refused to db-secret-host"),
    ):
        response = client.get(URL)

    assert response.status_code == 503
    # Solo el contrato: ni el mensaje de la excepción ni datos del host.
    assert response.json() == {"status": "error", "database": "error"}
    assert b"db-secret-host" not in response.content


# La página 403 de CSRF extiende base.html, que lee el nombre del negocio de los
# parámetros globales (SPEC 06).
@pytest.mark.django_db
def test_health_post_without_csrf_token_is_forbidden(csrf_client):
    response = csrf_client.post(URL)

    assert response.status_code == 403


def test_health_post_with_valid_csrf_token_is_not_allowed(csrf_client, csrf_token):
    csrf_client.cookies["csrftoken"] = csrf_token

    response = csrf_client.post(URL, headers={"X-CSRFToken": csrf_token})

    assert response.status_code == 405
