"""Pruebas de la vigencia de las versiones de tasa y de tope (SPEC 08, §3.3).

Hoy está fijado en el 13 de noviembre de 2026 (fixture `today`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.auditoria.models import AuditEvent
from apps.parametros.models import ProductRateVersion, RateCapType, RateCapValue
from apps.parametros.services import (
    ProductRuleError,
    get_rate_cap_value,
    get_rate_version,
    schedule_rate_cap_value,
    schedule_rate_version,
    void_rate_cap_value,
    void_rate_version,
)

pytestmark = pytest.mark.django_db

NOV_13 = date(2026, 11, 13)
NOV_30 = date(2026, 11, 30)
DEC_1 = date(2026, 12, 1)


def rate(product, user, valid_from: date, **fields) -> ProductRateVersion:
    values = {
        "product": product,
        "valid_from": valid_from,
        "min_rate": Decimal("10"),
        "default_rate": Decimal("20"),
        "max_rate": Decimal("25"),
        "created_by": user,
    }
    values.update(fields)
    return ProductRateVersion.objects.create(**values)


def cap_value(cap_type, user, valid_from: date, **fields) -> RateCapValue:
    values = {
        "cap_type": cap_type,
        "valid_from": valid_from,
        "annual_effective_rate": Decimal("25.5"),
        "created_by": user,
    }
    values.update(fields)
    return RateCapValue.objects.create(**values)


@pytest.fixture
def product(make_product):
    return make_product()


@pytest.fixture
def cap_type():
    return RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")


# Versiones de tasa


def test_without_versions_there_is_no_current_rate(product, today):
    assert get_rate_version(product) is None
    assert get_rate_version(product, on=date(2030, 1, 1)) is None


def test_current_version_is_the_latest_started(product, user, today):
    first = rate(product, user, NOV_13, valid_to=NOV_30)
    second = rate(product, user, DEC_1)

    assert get_rate_version(product, on=NOV_30) == first
    assert get_rate_version(product, on=DEC_1) == second
    assert get_rate_version(product, on=date(2027, 6, 1)) == second
    assert get_rate_version(product, on=date(2026, 11, 12)) is None


def test_on_defaults_to_today(product, user, today):
    first = rate(product, user, NOV_13, valid_to=NOV_30)
    rate(product, user, DEC_1)

    assert timezone.localdate() == NOV_13
    assert get_rate_version(product) == first


def test_voided_versions_are_ignored(product, user, today):
    first = rate(product, user, NOV_13)
    rate(product, user, DEC_1, voided_at=timezone.now(), voided_by=user)

    assert get_rate_version(product, on=DEC_1) == first


def test_versions_of_other_products_are_ignored(product, make_product, user, today):
    other = make_product("Semanal")
    rate(other, user, NOV_13)

    assert get_rate_version(product, on=NOV_13) is None


# Valores de tope


def test_without_values_there_is_no_current_cap_value(cap_type, today):
    assert get_rate_cap_value(cap_type) is None


def test_current_cap_value_is_the_latest_started(cap_type, user, today):
    first = cap_value(cap_type, user, NOV_13, valid_to=NOV_30)
    second = cap_value(cap_type, user, DEC_1, annual_effective_rate=Decimal("26"))

    assert get_rate_cap_value(cap_type) == first
    assert get_rate_cap_value(cap_type, on=NOV_30) == first
    assert get_rate_cap_value(cap_type, on=DEC_1) == second
    assert get_rate_cap_value(cap_type, on=date(2026, 11, 12)) is None


def test_voided_cap_values_are_ignored(cap_type, user, today):
    first = cap_value(cap_type, user, NOV_13)
    cap_value(cap_type, user, DEC_1, voided_at=timezone.now(), voided_by=user)

    assert get_rate_cap_value(cap_type, on=DEC_1) == first


# Programar y anular (§3.3). Cada prueba corre con las versiones de tasa de un
# producto y con los valores de un tope: las reglas son las mismas.


@dataclass
class History:
    """Un historial de versiones, de un producto o de un tipo de tope."""

    owner: Any
    schedule_service: Callable[..., Any]
    void_service: Callable[..., Any]
    data: dict[str, Any]
    current: Callable[..., Any]

    def schedule(self, actor, valid_from: date):
        return self.schedule_service(
            actor, self.owner, {**self.data, "valid_from": valid_from}
        )

    def void(self, actor, version):
        return self.void_service(actor, version)

    def versions(self):
        return self.owner_versions().order_by("pk")

    def owner_versions(self):
        if isinstance(self.owner, RateCapType):
            return self.owner.values.all()
        return self.owner.rate_versions.all()


@pytest.fixture(params=["tasa", "tope"])
def history(request, make_product, cap_type) -> History:
    if request.param == "tasa":
        return History(
            owner=make_product(),
            schedule_service=schedule_rate_version,
            void_service=void_rate_version,
            data={"min_rate": "10", "default_rate": "20", "max_rate": "25"},
            current=get_rate_version,
        )
    return History(
        owner=cap_type,
        schedule_service=schedule_rate_cap_value,
        void_service=void_rate_cap_value,
        data={"annual_effective_rate": "25.02", "reference": "Resolución 1 de 2026"},
        current=get_rate_cap_value,
    )


def test_version_cannot_start_in_the_past(history, product_editor, today):
    with pytest.raises(ValidationError) as excinfo:
        history.schedule(product_editor, date(2026, 11, 12))

    assert excinfo.value.message_dict["valid_from"] == [
        "La vigencia no puede empezar en una fecha pasada."
    ]
    assert not history.versions().exists()


def test_new_version_closes_the_previous_one(history, product_editor, today):
    first = history.schedule(product_editor, NOV_13)
    second = history.schedule(product_editor, DEC_1)

    first.refresh_from_db()
    assert first.valid_to == NOV_30
    assert second.valid_to is None
    assert second.created_by == product_editor
    assert history.current(history.owner, on=NOV_30) == first
    assert history.current(history.owner, on=DEC_1) == second
    assert history.current(history.owner) == first


def test_new_version_must_start_after_the_last_one(history, product_editor, today):
    history.schedule(product_editor, NOV_13)
    history.schedule(product_editor, DEC_1)

    for day in (date(2026, 11, 20), DEC_1):
        with pytest.raises(ValidationError) as excinfo:
            history.schedule(product_editor, day)
        assert excinfo.value.message_dict["valid_from"] == [
            "La vigencia tiene que empezar después del 01/12/2026, cuando empieza "
            "la última versión. Para corregir una versión programada, anúlala "
            "primero."
        ]

    assert history.versions().count() == 2


def test_second_version_from_today_fails(history, product_editor, today):
    history.schedule(product_editor, NOV_13)

    with pytest.raises(ValidationError) as excinfo:
        history.schedule(product_editor, NOV_13)

    assert "valid_from" in excinfo.value.message_dict


def test_voiding_the_scheduled_version_reopens_the_previous(
    history, product_editor, today
):
    first = history.schedule(product_editor, NOV_13)
    second = history.schedule(product_editor, DEC_1)

    history.void(product_editor, second)

    second.refresh_from_db()
    first.refresh_from_db()
    assert second.voided_at is not None
    assert second.voided_by == product_editor
    assert second.valid_to is None
    assert first.valid_to is None
    assert history.current(history.owner, on=DEC_1) == first


def test_voided_date_can_be_scheduled_again(history, product_editor, today):
    history.schedule(product_editor, NOV_13)
    second = history.schedule(product_editor, DEC_1)
    history.void(product_editor, second)

    third = history.schedule(product_editor, DEC_1)

    assert history.current(history.owner, on=DEC_1) == third


def test_voiding_the_only_scheduled_version_leaves_no_current(
    history, product_editor, today
):
    only = history.schedule(product_editor, DEC_1)

    history.void(product_editor, only)

    assert history.current(history.owner, on=DEC_1) is None


def test_version_that_rules_today_cannot_be_voided(history, product_editor, today):
    version = history.schedule(product_editor, NOV_13)
    before = AuditEvent.objects.count()

    with pytest.raises(ProductRuleError):
        history.void(product_editor, version)

    version.refresh_from_db()
    assert version.voided_at is None
    assert AuditEvent.objects.count() == before


def test_version_that_already_ruled_cannot_be_voided(
    history, product_editor, today, monkeypatch
):
    from django.utils import timezone as django_timezone

    monkeypatch.setattr(django_timezone, "localdate", lambda *a, **k: date(2026, 11, 1))
    old = history.schedule(product_editor, date(2026, 11, 1))
    monkeypatch.setattr(django_timezone, "localdate", lambda *a, **k: NOV_13)
    before = AuditEvent.objects.count()

    with pytest.raises(ProductRuleError) as excinfo:
        history.void(product_editor, old)

    assert excinfo.value.messages == [
        "Esa versión ya rige o ya rigió, y un crédito pudo haberla usado: no se "
        "puede anular. Programa una nueva."
    ]
    assert AuditEvent.objects.count() == before


def test_voided_version_cannot_be_voided_again(history, product_editor, today):
    version = history.schedule(product_editor, DEC_1)
    history.void(product_editor, version)
    before = AuditEvent.objects.count()

    with pytest.raises(ProductRuleError) as excinfo:
        history.void(product_editor, version)

    assert excinfo.value.messages == ["Esa versión ya está anulada."]
    assert AuditEvent.objects.count() == before


def test_only_the_last_version_can_be_voided(history, product_editor, today):
    first = history.schedule(product_editor, DEC_1)
    history.schedule(product_editor, date(2026, 12, 15))
    before = AuditEvent.objects.count()

    with pytest.raises(ProductRuleError) as excinfo:
        history.void(product_editor, first)

    assert excinfo.value.messages == [
        "Solo se puede anular la última versión programada."
    ]
    first.refresh_from_db()
    assert first.voided_at is None
    assert AuditEvent.objects.count() == before


def test_invalid_rates_are_reported_by_field(make_product, product_editor, today):
    with pytest.raises(ValidationError) as excinfo:
        schedule_rate_version(
            product_editor,
            make_product(),
            {
                "min_rate": "10",
                "default_rate": "20",
                "max_rate": "100.0001",
                "valid_from": DEC_1,
            },
        )

    assert "max_rate" in excinfo.value.message_dict


def test_invalid_cap_value_is_reported_by_field(cap_type, product_editor, today):
    with pytest.raises(ValidationError) as excinfo:
        schedule_rate_cap_value(
            product_editor,
            cap_type,
            {"annual_effective_rate": "0", "valid_from": DEC_1},
        )

    assert excinfo.value.message_dict["annual_effective_rate"] == [
        "El valor del tope debe ser mayor que cero."
    ]


def test_scheduling_ignores_valid_to_and_voided_fields(
    make_product, product_editor, user, today
):
    version = schedule_rate_version(
        product_editor,
        make_product(),
        {
            "min_rate": "10",
            "default_rate": "20",
            "max_rate": "25",
            "valid_from": DEC_1,
            "valid_to": DEC_1,
            "voided_by": user,
            "created_by": user,
        },
    )

    assert version.valid_to is None
    assert version.voided_by is None
    assert version.created_by == product_editor
