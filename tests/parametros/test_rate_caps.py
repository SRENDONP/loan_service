"""Pruebas de los tipos de tope de tasa (SPEC 08, §3.4)."""

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied

from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent
from apps.parametros.catalogs import (
    CATALOGS,
    RATE_CAP_CATALOG,
    RATE_CAP_USURY,
)
from apps.parametros.models import (
    CreditProduct,
    InterestMethod,
    Periodicity,
    RateCapType,
)
from apps.parametros.services import (
    CatalogRuleError,
    create_catalog_item,
    deactivate_catalog_item,
    get_item_by_code,
    reactivate_catalog_item,
    update_catalog_item,
)

pytestmark = pytest.mark.django_db


def usury() -> RateCapType:
    return RateCapType.objects.get(code=RATE_CAP_USURY)


def internal_cap(**fields: Any) -> RateCapType:
    values = {"code": "TOPE_INTERNO", "name": "Tope interno"}
    values.update(fields)
    return RateCapType.objects.create(**values)


def make_product(name: str = "Diario 20", **fields: Any) -> CreditProduct:
    values: dict[str, Any] = {
        "name": name,
        "interest_method": InterestMethod.FLAT_PER_CREDIT,
        "allowed_periodicities": [Periodicity.DAILY],
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
    values.update(fields)
    return CreditProduct.objects.create(**values)


# Carga inicial


def test_migrate_creates_usury_as_an_active_system_item_without_values():
    item = usury()

    assert item.name == "Usura"
    assert item.is_active
    assert item.is_system
    assert not item.values.exists()


def test_usury_is_the_only_initial_rate_cap_type():
    assert list(RateCapType.objects.values_list("code", flat=True)) == [RATE_CAP_USURY]


def test_usury_is_found_by_its_code():
    assert get_item_by_code(RateCapType, RATE_CAP_USURY) == usury()


# El catálogo


def test_rate_cap_catalog_points_to_rate_cap_type():
    assert RATE_CAP_CATALOG.model is RateCapType
    assert RATE_CAP_CATALOG.slug == "topes-tasa"
    assert str(RATE_CAP_CATALOG.label) == "Topes de tasa"
    assert RATE_CAP_CATALOG.permission("view") == "parametros.view_ratecaptype"


def test_rate_cap_catalog_is_not_in_the_catalogs_submenu():
    assert RateCapType not in {catalog.model for catalog in CATALOGS}


# Servicios de catálogos con `RATE_CAP_CATALOG`


def test_create_update_and_deactivate_use_the_catalog_audit(product_editor):
    item = create_catalog_item(
        product_editor, RATE_CAP_CATALOG, {"name": "Tope interno", "display_order": 20}
    )
    update_catalog_item(product_editor, item, {"name": "Tope interno del negocio"})
    deactivate_catalog_item(product_editor, item)
    reactivate_catalog_item(product_editor, item)

    content_type = ContentType.objects.get_for_model(RateCapType)
    actions = list(
        AuditEvent.objects.filter(content_type=content_type, object_id=str(item.pk))
        .order_by("pk")
        .values_list("action", flat=True)
    )
    assert actions == [
        AuditAction.CATALOG_ITEM_CREATED,
        AuditAction.CATALOG_ITEM_UPDATED,
        AuditAction.CATALOG_ITEM_DEACTIVATED,
        AuditAction.CATALOG_ITEM_REACTIVATED,
    ]
    assert item.code == "TOPE_INTERNO"
    assert not item.is_system


def test_catalog_services_need_the_rate_cap_permissions(catalog_editor):
    # `catalog_editor` tiene los permisos de los siete modelos de la SPEC 07.
    with pytest.raises(PermissionDenied):
        create_catalog_item(catalog_editor, RATE_CAP_CATALOG, {"name": "Tope"})


# Desactivación


def test_usury_cannot_be_deactivated(product_editor):
    with pytest.raises(CatalogRuleError) as excinfo:
        deactivate_catalog_item(product_editor, usury())

    assert excinfo.value.messages == ["Un ítem de sistema no se puede desactivar."]
    assert usury().is_active


def test_cap_used_by_an_active_product_cannot_be_deactivated(product_editor):
    cap = internal_cap()
    make_product("Semanal", additional_rate_cap=cap)
    make_product("Diario", additional_rate_cap=cap)
    before = AuditEvent.objects.count()

    with pytest.raises(CatalogRuleError) as excinfo:
        deactivate_catalog_item(product_editor, cap)

    assert excinfo.value.messages == [
        "Lo usa el producto Diario. Quítalo del producto antes de desactivarlo."
    ]
    cap.refresh_from_db()
    assert cap.is_active
    assert AuditEvent.objects.count() == before


def test_cap_used_only_by_inactive_products_is_deactivated(product_editor):
    cap = internal_cap()
    make_product(additional_rate_cap=cap, is_active=False)

    deactivate_catalog_item(product_editor, cap)

    cap.refresh_from_db()
    assert not cap.is_active


def test_cap_without_products_is_deactivated(product_editor):
    cap = internal_cap()

    deactivate_catalog_item(product_editor, cap)

    cap.refresh_from_db()
    assert not cap.is_active
