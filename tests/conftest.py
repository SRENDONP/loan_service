"""Fixtures compartidas por toda la suite."""

from typing import Any

import pytest
from django.test import Client

CSRF_TOKEN = "abcdefghijklmnopqrstuvwxyzABCDEF"

VALID_PASSWORD = "cobro2026"

FAST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def fast_password_hashers(settings) -> None:
    """
    Usa MD5 en las pruebas para que sean rápidas.

    Argon2 es deliberadamente lento. La configuración real del proyecto se
    comprueba en tests/accounts/test_settings.py.
    """
    settings.PASSWORD_HASHERS = FAST_PASSWORD_HASHERS


@pytest.fixture
def password() -> str:
    """Contraseña que cumple la política del proyecto."""
    return VALID_PASSWORD


@pytest.fixture
def make_user(db):
    """
    Crea usuarios de prueba con una contraseña válida.

    Por defecto el usuario no tiene que cambiar la contraseña, para que las
    pruebas que no tratan de eso no pasen por el middleware de cambio
    obligatorio. Cualquier campo se puede cambiar con un argumento.

    `role` asigna uno de los cuatro roles (SPEC 04); por defecto no tiene rol.
    Los grupos ya existen porque `migrate` los crea con `sync_roles`.
    """
    from django.contrib.auth.models import Group

    from apps.accounts.models import User

    def factory(username: str = "cobrador", *, role: Any = None, **fields: Any) -> User:
        fields.setdefault("password", VALID_PASSWORD)
        fields.setdefault("must_change_password", False)
        user = User.objects.create_user(username=username, **fields)
        if role is not None:
            user.groups.add(Group.objects.get(name=role))
        return user

    return factory


@pytest.fixture
def user(make_user):
    """Usuario activo que no tiene que cambiar la contraseña."""
    return make_user()


@pytest.fixture
def auth_client(client: Client, user) -> Client:
    """Cliente con la sesión de `user` abierta. Todo el sistema exige sesión."""
    client.force_login(user)
    return client


@pytest.fixture
def csrf_client() -> Client:
    """Cliente que aplica la validación CSRF, como un navegador real."""
    return Client(enforce_csrf_checks=True)


@pytest.fixture
def csrf_token() -> str:
    """Token CSRF válido para usar en la cookie y en la cabecera X-CSRFToken."""
    return CSRF_TOKEN


@pytest.fixture
def global_settings(db):
    """
    La fila de parámetros globales (SPEC 06), lista para cambiar en una prueba.

    Se cambian los atributos y se llama a `save()`; el cambio se revierte con la
    transacción de la prueba. Reemplaza a `override_settings` para los valores
    que ahora viven en `parametros`.
    """
    from apps.parametros.services import get_settings

    return get_settings()
