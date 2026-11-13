"""Pruebas de la auditoría de catálogos y festivos (SPEC 07, §3.8)."""

from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from apps.auditoria.actions import ACTION_CATEGORIES, AuditAction, AuditCategory
from apps.auditoria.models import AuditEvent
from apps.parametros import services
from apps.parametros.catalogs import RELATION_CODEBTOR, get_catalog
from apps.parametros.models import Holiday, Occupation, ThirdPartyRelationType
from apps.parametros.services import (
    CatalogRuleError,
    create_catalog_item,
    create_holiday,
    deactivate_catalog_item,
    deactivate_holiday,
    load_official_holidays,
    reactivate_catalog_item,
    reactivate_holiday,
    update_catalog_item,
    update_holiday,
)

pytestmark = pytest.mark.django_db

CATALOG_ACTIONS = {
    AuditAction.CATALOG_ITEM_CREATED: "catalogos.item_created",
    AuditAction.CATALOG_ITEM_UPDATED: "catalogos.item_updated",
    AuditAction.CATALOG_ITEM_DEACTIVATED: "catalogos.item_deactivated",
    AuditAction.CATALOG_ITEM_REACTIVATED: "catalogos.item_reactivated",
}
HOLIDAY_ACTIONS = {
    AuditAction.HOLIDAY_CREATED: "festivos.created",
    AuditAction.HOLIDAY_UPDATED: "festivos.updated",
    AuditAction.HOLIDAY_DEACTIVATED: "festivos.deactivated",
    AuditAction.HOLIDAY_REACTIVATED: "festivos.reactivated",
    AuditAction.HOLIDAYS_LOADED: "festivos.loaded",
}
ALL_ACTIONS = [*CATALOG_ACTIONS, *HOLIDAY_ACTIONS]

FREE_DAY = date(2026, 2, 14)


def events():
    return AuditEvent.objects.filter(action__in=ALL_ACTIONS)


def is_target(event: AuditEvent, instance) -> bool:
    """Si la entidad del registro es `instance` (tipo de contenido y `pk`)."""
    return (
        event.content_type == ContentType.objects.get_for_model(instance)
        and event.object_id == str(instance.pk)
        and event.object_repr == str(instance)
    )


def tendero() -> Occupation:
    return Occupation.objects.get(code="TENDERO")


def reyes_2026() -> Holiday:
    return Holiday.objects.get(official_year=2026, official_code="reyes_magos")


# Catálogo de acciones


@pytest.mark.parametrize(
    ("action", "value"), [*CATALOG_ACTIONS.items(), *HOLIDAY_ACTIONS.items()]
)
def test_action_values(action, value):
    assert action.value == value


@pytest.mark.parametrize("action", CATALOG_ACTIONS)
def test_catalog_actions_are_security(action):
    assert ACTION_CATEGORIES[action] == AuditCategory.SECURITY


@pytest.mark.parametrize("action", HOLIDAY_ACTIONS)
def test_holiday_actions_are_financial(action):
    assert ACTION_CATEGORIES[action] == AuditCategory.FINANCIAL


# Catálogos de texto


def test_create_records_all_auditable_fields_with_none_before(catalog_editor):
    item = create_catalog_item(
        catalog_editor,
        get_catalog("ocupaciones"),
        {"name": "Vendedor de feria", "display_order": 90},
    )

    event = events().get()
    assert event.action == AuditAction.CATALOG_ITEM_CREATED
    assert event.category == AuditCategory.SECURITY
    assert event.actor == catalog_editor
    assert is_target(event, item)
    assert event.changes == {
        "code": [None, "VENDEDOR_DE_FERIA"],
        "name": [None, "Vendedor de feria"],
        "display_order": [None, 90],
        "is_active": [None, True],
    }


def test_update_records_only_the_changed_fields(catalog_editor):
    update_catalog_item(catalog_editor, tendero(), {"name": "Tendero de barrio"})

    event = events().get()
    assert event.action == AuditAction.CATALOG_ITEM_UPDATED
    assert is_target(event, tendero())
    assert event.changes == {"name": ["Tendero", "Tendero de barrio"]}


def test_update_without_changes_records_nothing(catalog_editor):
    update_catalog_item(catalog_editor, tendero(), {"name": "Tendero"})

    assert not events().exists()


def test_update_ignored_fields_are_not_recorded(catalog_editor):
    update_catalog_item(catalog_editor, tendero(), {"code": "OTRO", "is_active": False})

    assert not events().exists()


def test_deactivate_and_reactivate_record_the_state(catalog_editor):
    deactivate_catalog_item(catalog_editor, tendero())
    reactivate_catalog_item(catalog_editor, tendero())

    deactivated, reactivated = events().order_by("pk")
    assert deactivated.action == AuditAction.CATALOG_ITEM_DEACTIVATED
    assert deactivated.changes == {"is_active": [True, False]}
    assert reactivated.action == AuditAction.CATALOG_ITEM_REACTIVATED
    assert reactivated.changes == {"is_active": [False, True]}
    assert is_target(reactivated, tendero())


def test_rule_errors_record_nothing(catalog_editor):
    codebtor = ThirdPartyRelationType.objects.get(code=RELATION_CODEBTOR)

    with pytest.raises(CatalogRuleError):
        deactivate_catalog_item(catalog_editor, codebtor)
    with pytest.raises(CatalogRuleError):
        reactivate_catalog_item(catalog_editor, tendero())

    assert not events().exists()


def test_invalid_create_records_nothing(catalog_editor):
    with pytest.raises(ValidationError):
        create_catalog_item(
            catalog_editor, get_catalog("ocupaciones"), {"name": "tendero"}
        )

    assert not events().exists()


def test_denied_catalog_actions_record_nothing(no_perms_user):
    with pytest.raises(PermissionDenied):
        create_catalog_item(no_perms_user, get_catalog("ocupaciones"), {"name": "X"})
    with pytest.raises(PermissionDenied):
        deactivate_catalog_item(no_perms_user, tendero())

    assert not events().exists()


# Festivos


def test_create_holiday_records_its_fields(catalog_editor):
    holiday = create_holiday(catalog_editor, {"date": FREE_DAY, "name": "Propio"})

    event = events().get()
    assert event.action == AuditAction.HOLIDAY_CREATED
    assert event.category == AuditCategory.FINANCIAL
    assert event.actor == catalog_editor
    assert is_target(event, holiday)
    assert event.changes == {
        "date": [None, "2026-02-14"],
        "name": [None, "Propio"],
        "origin": [None, "custom"],
        "is_active": [None, True],
    }


def test_update_holiday_records_the_date_in_iso_format(catalog_editor):
    update_holiday(catalog_editor, reyes_2026(), {"date": date(2026, 1, 6)})

    event = events().get()
    assert event.action == AuditAction.HOLIDAY_UPDATED
    assert is_target(event, reyes_2026())
    assert event.changes == {"date": ["2026-01-12", "2026-01-06"]}


def test_update_holiday_without_changes_records_nothing(catalog_editor):
    update_holiday(catalog_editor, reyes_2026(), {"name": reyes_2026().name})

    assert not events().exists()


def test_deactivate_and_reactivate_holiday_record_the_state(catalog_editor):
    deactivate_holiday(catalog_editor, reyes_2026())
    reactivate_holiday(catalog_editor, reyes_2026())

    deactivated, reactivated = events().order_by("pk")
    assert deactivated.action == AuditAction.HOLIDAY_DEACTIVATED
    assert deactivated.changes == {"is_active": [True, False]}
    assert reactivated.action == AuditAction.HOLIDAY_REACTIVATED
    assert reactivated.changes == {"is_active": [False, True]}


def test_load_records_one_event_without_target():
    load_official_holidays(2031)

    event = events().get()
    assert event.action == AuditAction.HOLIDAYS_LOADED
    assert event.category == AuditCategory.FINANCIAL
    assert event.actor is None
    assert event.content_type is None
    assert event.extra == {"year": 2031, "created": 18}


def test_denied_holiday_actions_record_nothing(no_perms_user):
    with pytest.raises(PermissionDenied):
        create_holiday(no_perms_user, {"date": FREE_DAY, "name": "Propio"})
    with pytest.raises(PermissionDenied):
        update_holiday(no_perms_user, reyes_2026(), {"name": "Otro"})

    assert not events().exists()


# Reversión si `record` falla


@pytest.fixture
def broken_record(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("falla de auditoría")

    monkeypatch.setattr(services, "record", broken)


def test_failed_record_rolls_back_create(catalog_editor, broken_record):
    with pytest.raises(RuntimeError):
        create_catalog_item(
            catalog_editor, get_catalog("ocupaciones"), {"name": "Vendedor de feria"}
        )

    assert not Occupation.objects.filter(name="Vendedor de feria").exists()


def test_failed_record_rolls_back_update(catalog_editor, broken_record):
    with pytest.raises(RuntimeError):
        update_catalog_item(catalog_editor, tendero(), {"name": "Tendero de barrio"})

    assert tendero().name == "Tendero"


def test_failed_record_rolls_back_deactivate(catalog_editor, broken_record):
    with pytest.raises(RuntimeError):
        deactivate_catalog_item(catalog_editor, tendero())

    assert tendero().is_active


def test_failed_record_rolls_back_holiday_create(catalog_editor, broken_record):
    with pytest.raises(RuntimeError):
        create_holiday(catalog_editor, {"date": FREE_DAY, "name": "Propio"})

    assert not Holiday.objects.filter(date=FREE_DAY).exists()


def test_failed_record_rolls_back_holiday_update(catalog_editor, broken_record):
    with pytest.raises(RuntimeError):
        update_holiday(catalog_editor, reyes_2026(), {"name": "Reyes"})

    assert reyes_2026().name == "Día de los Reyes Magos"


def test_failed_record_rolls_back_holiday_deactivate(catalog_editor, broken_record):
    with pytest.raises(RuntimeError):
        deactivate_holiday(catalog_editor, reyes_2026())

    assert reyes_2026().is_active


def test_failed_record_rolls_back_the_whole_load(broken_record):
    with pytest.raises(RuntimeError):
        load_official_holidays(2031)

    assert not Holiday.objects.filter(official_year=2031).exists()
