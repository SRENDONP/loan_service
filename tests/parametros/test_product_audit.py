"""Pruebas de la auditoría de productos, tasas y topes (SPEC 08, §3.6).

Hoy está fijado en el 13 de noviembre de 2026 (fixture `today`).
"""

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType

from apps.auditoria.actions import ACTION_CATEGORIES, AuditAction, AuditCategory
from apps.auditoria.models import AuditEvent
from apps.parametros import services
from apps.parametros.models import (
    CreditProduct,
    ProductRateVersion,
    RateCapType,
    RateCapValue,
)
from apps.parametros.services import (
    PRODUCT_AUDIT_FIELDS,
    create_product,
    deactivate_product,
    reactivate_product,
    schedule_rate_cap_value,
    schedule_rate_version,
    update_product,
    void_rate_cap_value,
    void_rate_version,
)
from tests.parametros.conftest import product_fields

pytestmark = pytest.mark.django_db

NOV_13 = date(2026, 11, 13)
DEC_1 = date(2026, 12, 1)

PRODUCT_ACTIONS = {
    AuditAction.PRODUCT_CREATED: "productos.created",
    AuditAction.PRODUCT_UPDATED: "productos.updated",
    AuditAction.PRODUCT_DEACTIVATED: "productos.deactivated",
    AuditAction.PRODUCT_REACTIVATED: "productos.reactivated",
    AuditAction.PRODUCT_RATE_SCHEDULED: "productos.rate_scheduled",
    AuditAction.PRODUCT_RATE_VOIDED: "productos.rate_voided",
    AuditAction.RATE_CAP_VALUE_SCHEDULED: "topes.value_scheduled",
    AuditAction.RATE_CAP_VALUE_VOIDED: "topes.value_voided",
}

RATE = {"min_rate": "10", "default_rate": "20", "max_rate": "25"}
CAP_VALUE = {"annual_effective_rate": "25.02", "reference": "Resolución 1 de 2026"}


def events():
    return AuditEvent.objects.filter(action__in=PRODUCT_ACTIONS).order_by("pk")


def is_target(event: AuditEvent, instance) -> bool:
    return (
        event.content_type == ContentType.objects.get_for_model(instance)
        and event.object_id == str(instance.pk)
        and event.object_repr == str(instance)
    )


@pytest.fixture
def cap_type():
    return RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")


@pytest.fixture
def product(product_editor, today):
    return create_product(
        product_editor, product_fields(), {**RATE, "valid_from": NOV_13}
    )


# El catálogo de acciones


@pytest.mark.parametrize(("action", "value"), PRODUCT_ACTIONS.items())
def test_action_values_and_category(action, value):
    assert action.value == value
    assert ACTION_CATEGORIES[action] == AuditCategory.FINANCIAL


# Cada servicio deja su acción


def test_create_product_records_product_and_first_rate(product_editor, product):
    created, scheduled = events()
    version = product.rate_versions.get()

    assert created.action == AuditAction.PRODUCT_CREATED
    assert scheduled.action == AuditAction.PRODUCT_RATE_SCHEDULED
    for event in (created, scheduled):
        assert event.category == AuditCategory.FINANCIAL
        assert event.actor == product_editor
    assert is_target(created, product)
    assert is_target(scheduled, version)


def test_creation_changes_have_every_auditable_field_with_none_before(product):
    created, scheduled = events()

    assert set(created.changes) <= set(PRODUCT_AUDIT_FIELDS)
    assert created.changes["name"] == [None, "Diario 20"]
    assert created.changes["min_amount"] == [None, "50000.00"]
    assert created.changes["late_fee_daily_rate"] == [None, "1.0000"]
    assert created.changes["allowed_periodicities"] == [None, ["daily", "weekly"]]
    assert created.changes["is_active"] == [None, True]
    assert "updated_by" not in created.changes
    assert "created_at" not in created.changes
    assert scheduled.changes == {
        "min_rate": [None, "10.0000"],
        "default_rate": [None, "20.0000"],
        "max_rate": [None, "25.0000"],
        "valid_from": [None, "2026-11-13"],
    }
    assert scheduled.extra == {}


def test_update_records_only_what_changed(product_editor, product):
    update_product(product_editor, product, {"max_installments": 60, "name": "Diario"})

    event = events().get(action=AuditAction.PRODUCT_UPDATED)
    assert event.actor == product_editor
    assert event.category == AuditCategory.FINANCIAL
    assert event.changes == {
        "name": ["Diario 20", "Diario"],
        "max_installments": [40, 60],
    }
    product.refresh_from_db()
    assert is_target(event, product)


def test_update_without_changes_does_not_record(product_editor, product):
    update_product(product_editor, product, {"name": "Diario 20"})

    assert not events().filter(action=AuditAction.PRODUCT_UPDATED).exists()


def test_deactivate_and_reactivate_record_the_state(product_editor, product):
    deactivate_product(product_editor, product)
    reactivate_product(product_editor, product)

    deactivated = events().get(action=AuditAction.PRODUCT_DEACTIVATED)
    reactivated = events().get(action=AuditAction.PRODUCT_REACTIVATED)
    assert deactivated.changes == {"is_active": [True, False]}
    assert reactivated.changes == {"is_active": [False, True]}
    for event in (deactivated, reactivated):
        assert event.category == AuditCategory.FINANCIAL
        assert event.actor == product_editor
        assert is_target(event, product)


def test_scheduling_a_rate_that_closes_another_records_it(product_editor, product):
    first = product.rate_versions.get()

    second = schedule_rate_version(
        product_editor, product, {**RATE, "valid_from": DEC_1}
    )

    event = events().filter(action=AuditAction.PRODUCT_RATE_SCHEDULED).last()
    assert is_target(event, second)
    assert event.actor == product_editor
    assert event.extra == {"closed_pk": first.pk, "closed_valid_to": "2026-11-30"}


def test_voiding_a_rate_records_the_reopened_version(product_editor, product):
    first = product.rate_versions.get()
    second = schedule_rate_version(
        product_editor, product, {**RATE, "valid_from": DEC_1}
    )

    void_rate_version(product_editor, second)

    event = events().get(action=AuditAction.PRODUCT_RATE_VOIDED)
    second.refresh_from_db()
    assert is_target(event, second)
    assert event.actor == product_editor
    assert event.extra == {"reopened_pk": first.pk}
    assert event.changes["voided_by"] == [None, product_editor.pk]
    assert event.changes["voided_at"][0] is None


def test_cap_values_record_their_actions(product_editor, cap_type, today):
    first = schedule_rate_cap_value(
        product_editor, cap_type, {**CAP_VALUE, "valid_from": NOV_13}
    )
    second = schedule_rate_cap_value(
        product_editor, cap_type, {**CAP_VALUE, "valid_from": DEC_1}
    )
    void_rate_cap_value(product_editor, second)

    scheduled_first, scheduled_second, voided = events()
    assert scheduled_first.action == AuditAction.RATE_CAP_VALUE_SCHEDULED
    assert is_target(scheduled_first, first)
    assert scheduled_first.changes == {
        "annual_effective_rate": [None, "25.0200"],
        "valid_from": [None, "2026-11-13"],
        "reference": [None, "Resolución 1 de 2026"],
    }
    assert scheduled_second.extra == {
        "closed_pk": first.pk,
        "closed_valid_to": "2026-11-30",
    }
    assert voided.action == AuditAction.RATE_CAP_VALUE_VOIDED
    assert voided.extra == {"reopened_pk": first.pk}
    for event in (scheduled_first, scheduled_second, voided):
        assert event.category == AuditCategory.FINANCIAL
        assert event.actor == product_editor


# Si `record` falla, nada cambia


@pytest.fixture
def failing_record(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Falla la auditoría")

    monkeypatch.setattr(services, "record", fail)


def test_create_product_is_reverted_if_record_fails(
    product_editor, today, failing_record
):
    with pytest.raises(RuntimeError):
        create_product(product_editor, product_fields(), {**RATE, "valid_from": NOV_13})

    assert not CreditProduct.objects.exists()
    assert not ProductRateVersion.objects.exists()


def test_update_and_state_changes_are_reverted_if_record_fails(
    product_editor, product, monkeypatch
):
    monkeypatch.setattr(services, "record", _raise)

    with pytest.raises(RuntimeError):
        update_product(product_editor, product, {"name": "Otro"})
    with pytest.raises(RuntimeError):
        deactivate_product(product_editor, product)

    product.refresh_from_db()
    assert product.name == "Diario 20"
    assert product.is_active


def test_scheduling_is_reverted_with_the_previous_valid_to(
    product_editor, product, monkeypatch
):
    first = product.rate_versions.get()
    monkeypatch.setattr(services, "record", _raise)

    with pytest.raises(RuntimeError):
        schedule_rate_version(product_editor, product, {**RATE, "valid_from": DEC_1})

    first.refresh_from_db()
    assert first.valid_to is None
    assert product.rate_versions.count() == 1


def test_voiding_is_reverted_with_the_previous_valid_to(
    product_editor, product, monkeypatch
):
    first = product.rate_versions.get()
    second = schedule_rate_version(
        product_editor, product, {**RATE, "valid_from": DEC_1}
    )
    monkeypatch.setattr(services, "record", _raise)

    with pytest.raises(RuntimeError):
        void_rate_version(product_editor, second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.valid_to == date(2026, 11, 30)
    assert second.voided_at is None


def test_cap_value_scheduling_and_voiding_are_reverted(
    product_editor, cap_type, today, monkeypatch
):
    first = schedule_rate_cap_value(
        product_editor, cap_type, {**CAP_VALUE, "valid_from": NOV_13}
    )
    second = schedule_rate_cap_value(
        product_editor, cap_type, {**CAP_VALUE, "valid_from": DEC_1}
    )
    monkeypatch.setattr(services, "record", _raise)

    with pytest.raises(RuntimeError):
        schedule_rate_cap_value(
            product_editor, cap_type, {**CAP_VALUE, "valid_from": date(2026, 12, 15)}
        )
    with pytest.raises(RuntimeError):
        void_rate_cap_value(product_editor, second)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.valid_to == date(2026, 11, 30)
    assert second.valid_to is None
    assert second.voided_at is None
    assert RateCapValue.objects.filter(cap_type=cap_type).count() == 2


def _raise(*args, **kwargs):
    raise RuntimeError("Falla la auditoría")
