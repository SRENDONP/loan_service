"""Fixtures de las pruebas de catálogos y festivos (SPEC 07)."""

import pytest
from django.contrib.auth.models import Permission

CATALOG_MODEL_NAMES = (
    "documenttype",
    "occupation",
    "creditpurpose",
    "voidreason",
    "rejectionreason",
    "thirdpartyrelationtype",
    "holiday",
)


@pytest.fixture
def catalog_editor(make_user):
    """Un usuario con `add` y `change` de los siete modelos, sin rol."""
    user = make_user("editor_catalogos")
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="parametros",
            content_type__model__in=CATALOG_MODEL_NAMES,
            codename__regex=r"^(add|change)_",
        )
    )
    return user


@pytest.fixture
def no_perms_user(make_user):
    return make_user("sin_permisos")
