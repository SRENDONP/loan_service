"""Fixtures compartidas por toda la suite."""

import pytest
from django.test import Client

CSRF_TOKEN = "abcdefghijklmnopqrstuvwxyzABCDEF"


@pytest.fixture
def csrf_client() -> Client:
    """Cliente que aplica la validación CSRF, como un navegador real."""
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def csrf_token() -> str:
    """Token CSRF válido para usar en la cookie y en la cabecera X-CSRFToken."""
    return CSRF_TOKEN
