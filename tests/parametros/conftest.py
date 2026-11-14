"""Fixtures de las pruebas de catálogos y festivos (SPEC 07) y productos (SPEC 08)."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission

# El "hoy" de las pruebas de vigencias (SPEC 08, §5).
TODAY = date(2026, 11, 13)

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


PRODUCT_MODEL_NAMES = (
    "creditproduct",
    "productrateversion",
    "ratecaptype",
    "ratecapvalue",
)


@pytest.fixture
def product_editor(make_user):
    """Un usuario con `add` y `change` de los cuatro modelos de la SPEC 08, sin rol."""
    user = make_user("editor_productos")
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="parametros",
            content_type__model__in=PRODUCT_MODEL_NAMES,
            codename__regex=r"^(add|change)_",
        )
    )
    return user


@pytest.fixture
def today(monkeypatch) -> date:
    """
    Congela `timezone.localdate()` en el 13 de noviembre de 2026.

    Los servicios de la SPEC 08 leen "hoy" con esa función, así que ninguna
    prueba depende de la fecha real.
    """
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *args, **kwargs: TODAY)
    return TODAY


def product_fields(**overrides: Any) -> dict[str, Any]:
    """Los campos de un producto válido: plano fijo, diario, de 20 cuotas."""
    from apps.parametros.models import InterestMethod, Periodicity

    fields: dict[str, Any] = {
        "name": "Diario 20",
        "interest_method": InterestMethod.FLAT_PER_CREDIT,
        "allowed_periodicities": [Periodicity.DAILY, Periodicity.WEEKLY],
        "default_periodicity": Periodicity.DAILY,
        "min_amount": Decimal("50000"),
        "max_amount": Decimal("2000000"),
        "min_installments": 10,
        "default_installments": 20,
        "max_installments": 40,
        "late_fee_daily_rate": Decimal("1"),
        "late_fee_cap_percent": Decimal("20"),
        "write_off_min_days_past_due": 90,
    }
    fields.update(overrides)
    return fields


@pytest.fixture
def make_product(make_user):
    """
    Crea un producto con el ORM, sin servicios ni auditoría.

    Con `valid_from`, le crea también una versión de tasa (10 %, 20 % y 25 %)
    que rige desde esa fecha. Cualquier campo del producto se cambia con un
    argumento.
    """
    from apps.parametros.models import CreditProduct, ProductRateVersion

    creator: list[Any] = []

    def factory(
        name: str = "Diario 20", *, valid_from: date | None = None, **fields: Any
    ) -> CreditProduct:
        product = CreditProduct.objects.create(**product_fields(name=name, **fields))
        if valid_from is not None:
            if not creator:
                creator.append(make_user("creador_productos"))
            ProductRateVersion.objects.create(
                product=product,
                valid_from=valid_from,
                min_rate=Decimal("10"),
                default_rate=Decimal("20"),
                max_rate=Decimal("25"),
                created_by=creator[0],
            )
        return product

    return factory


@pytest.fixture
def no_perms_user(make_user):
    return make_user("sin_permisos")
