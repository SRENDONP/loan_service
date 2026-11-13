"""Pruebas de los servicios de festivos (SPEC 07, §3.6)."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError

from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent
from apps.parametros.models import Holiday, HolidayOrigin
from apps.parametros.services import (
    CatalogRuleError,
    create_holiday,
    deactivate_holiday,
    load_official_holidays,
    missing_official_years,
    reactivate_holiday,
    update_holiday,
)

pytestmark = pytest.mark.django_db

FREE_DAY = date(2026, 2, 14)  # sábado sin festivo
REYES_2026 = date(2026, 1, 12)


def reyes_2026() -> Holiday:
    return Holiday.objects.get(official_year=2026, official_code="reyes_magos")


# Crear y editar


def test_create_holiday_creates_a_custom_holiday(catalog_editor):
    holiday = create_holiday(
        catalog_editor, {"date": FREE_DAY, "name": " Aniversario del negocio "}
    )

    holiday.refresh_from_db()
    assert holiday.origin == HolidayOrigin.CUSTOM
    assert holiday.official_code == ""
    assert holiday.official_year is None
    assert holiday.name == "Aniversario del negocio"
    assert holiday.is_active
    assert holiday.updated_by == catalog_editor


def test_create_holiday_ignores_official_fields(catalog_editor):
    holiday = create_holiday(
        catalog_editor,
        {
            "date": FREE_DAY,
            "name": "Propio",
            "origin": HolidayOrigin.OFFICIAL,
            "official_code": "trampa",
            "official_year": 2026,
            "is_active": False,
        },
    )

    assert holiday.origin == HolidayOrigin.CUSTOM
    assert holiday.official_code == ""
    assert holiday.is_active


def test_create_holiday_on_an_occupied_date_fails_with_the_date(catalog_editor):
    with pytest.raises(ValidationError) as excinfo:
        create_holiday(catalog_editor, {"date": REYES_2026, "name": "Otro"})

    assert excinfo.value.message_dict["date"] == [
        "Ya hay un festivo activo el 12/01/2026."
    ]


def test_create_holiday_without_date_fails(catalog_editor):
    with pytest.raises(ValidationError) as excinfo:
        create_holiday(catalog_editor, {"name": "Sin fecha"})

    assert "date" in excinfo.value.message_dict


def test_create_holiday_without_permission_is_denied(no_perms_user):
    with pytest.raises(PermissionDenied):
        create_holiday(no_perms_user, {"date": FREE_DAY, "name": "Propio"})

    assert not Holiday.objects.filter(date=FREE_DAY).exists()


def test_update_official_holiday_keeps_origin_code_and_year(catalog_editor):
    holiday = update_holiday(
        catalog_editor,
        reyes_2026(),
        {"date": date(2026, 1, 6), "name": "Reyes", "origin": HolidayOrigin.CUSTOM},
    )

    holiday.refresh_from_db()
    assert holiday.date == date(2026, 1, 6)
    assert holiday.name == "Reyes"
    assert holiday.origin == HolidayOrigin.OFFICIAL
    assert holiday.official_code == "reyes_magos"
    assert holiday.official_year == 2026
    assert holiday.updated_by == catalog_editor


def test_update_holiday_to_another_year_keeps_its_official_year(catalog_editor):
    holiday = update_holiday(catalog_editor, reyes_2026(), {"date": date(2027, 1, 5)})

    assert holiday.official_year == 2026
    assert load_official_holidays(2026) == 0


def test_update_holiday_without_changes_does_not_save(catalog_editor):
    original = reyes_2026()

    result = update_holiday(
        catalog_editor, original, {"date": REYES_2026, "name": original.name}
    )

    result.refresh_from_db()
    assert result.updated_at == original.updated_at
    assert result.updated_by is None


def test_update_holiday_to_an_occupied_date_fails(catalog_editor):
    with pytest.raises(ValidationError) as excinfo:
        update_holiday(catalog_editor, reyes_2026(), {"date": date(2026, 1, 1)})

    assert "date" in excinfo.value.message_dict
    assert reyes_2026().date == REYES_2026


def test_update_holiday_without_permission_is_denied(no_perms_user):
    with pytest.raises(PermissionDenied):
        update_holiday(no_perms_user, reyes_2026(), {"name": "Otro"})


# Desactivar y reactivar


def test_deactivate_and_reactivate_holiday(catalog_editor):
    holiday = deactivate_holiday(catalog_editor, reyes_2026())
    assert not reyes_2026().is_active
    assert holiday.updated_by == catalog_editor

    reactivate_holiday(catalog_editor, holiday)
    assert reyes_2026().is_active


def test_deactivate_an_inactive_holiday_is_a_rule_error(catalog_editor):
    holiday = deactivate_holiday(catalog_editor, reyes_2026())

    with pytest.raises(CatalogRuleError) as excinfo:
        deactivate_holiday(catalog_editor, holiday)

    assert excinfo.value.messages == ["El festivo ya está inactivo."]


def test_reactivate_an_active_holiday_is_a_rule_error(catalog_editor):
    with pytest.raises(CatalogRuleError) as excinfo:
        reactivate_holiday(catalog_editor, reyes_2026())

    assert excinfo.value.messages == ["El festivo ya está activo."]


def test_reactivate_on_an_occupied_date_fails(catalog_editor):
    deactivate_holiday(catalog_editor, reyes_2026())
    create_holiday(catalog_editor, {"date": REYES_2026, "name": "Propio"})

    with pytest.raises(ValidationError) as excinfo:
        reactivate_holiday(catalog_editor, reyes_2026())

    assert "date" in excinfo.value.message_dict
    assert not reyes_2026().is_active


@pytest.mark.parametrize("service", [deactivate_holiday, reactivate_holiday])
def test_state_changes_without_permission_are_denied(no_perms_user, service):
    with pytest.raises(PermissionDenied):
        service(no_perms_user, reyes_2026())


# Carga de festivos oficiales


def test_load_creates_18_holidays_and_returns_18():
    assert load_official_holidays(2031) == 18

    loaded = Holiday.objects.filter(official_year=2031)
    assert loaded.count() == 18
    assert all(h.origin == HolidayOrigin.OFFICIAL for h in loaded)
    assert all(h.is_active for h in loaded)
    assert all(h.updated_by is None for h in loaded)


def test_load_twice_creates_nothing_and_records_nothing():
    load_official_holidays(2031)
    events = AuditEvent.objects.filter(action=AuditAction.HOLIDAYS_LOADED)
    assert events.count() == 1

    assert load_official_holidays(2031) == 0
    assert Holiday.objects.filter(official_year=2031).count() == 18
    assert events.count() == 1


def test_load_does_not_resurrect_a_deactivated_holiday(catalog_editor):
    holiday = Holiday.objects.get(official_year=2027, official_code="san_jose")
    deactivate_holiday(catalog_editor, holiday)

    assert load_official_holidays(2027) == 0

    same = Holiday.objects.filter(official_year=2027, official_code="san_jose")
    assert same.count() == 1
    assert not same.get().is_active


def test_load_does_not_move_an_edited_holiday(catalog_editor):
    update_holiday(catalog_editor, reyes_2026(), {"date": date(2026, 1, 6)})

    assert load_official_holidays(2026) == 0
    assert reyes_2026().date == date(2026, 1, 6)


def test_load_adds_only_the_missing_holidays():
    Holiday.objects.create(
        date=date(2031, 12, 24),
        name="Navidad corrida",
        origin=HolidayOrigin.OFFICIAL,
        official_code="navidad",
        official_year=2031,
    )

    assert load_official_holidays(2031) == 17
    navidad = Holiday.objects.get(official_year=2031, official_code="navidad")
    assert navidad.date == date(2031, 12, 24)
    assert navidad.name == "Navidad corrida"


def test_load_creates_the_official_inactive_on_a_date_with_a_custom_holiday(
    catalog_editor,
):
    reyes_2031 = date(2031, 1, 6)
    create_holiday(catalog_editor, {"date": reyes_2031, "name": "Propio"})

    load_official_holidays(2031)

    official = Holiday.objects.get(official_year=2031, official_code="reyes_magos")
    custom = Holiday.objects.get(date=reyes_2031, origin=HolidayOrigin.CUSTOM)
    assert not official.is_active
    assert custom.is_active


def test_load_with_actor_requires_the_add_permission(no_perms_user):
    with pytest.raises(PermissionDenied):
        load_official_holidays(2031, actor=no_perms_user)

    assert not Holiday.objects.filter(official_year=2031).exists()


def test_load_with_actor_records_the_actor(make_user):
    user = make_user("cargador")
    user.user_permissions.add(Permission.objects.get(codename="add_holiday"))

    load_official_holidays(2031, actor=user)

    event = AuditEvent.objects.get(action=AuditAction.HOLIDAYS_LOADED)
    assert event.actor == user
    assert Holiday.objects.filter(official_year=2031, updated_by=user).count() == 18


@pytest.mark.parametrize("year", [1983, 2101])
def test_load_out_of_range_raises_value_error(year):
    with pytest.raises(ValueError):
        load_official_holidays(year)


# Años sin carga


def test_missing_official_years():
    assert missing_official_years([2025, 2026, 2030, 2031, 2029]) == [2025, 2031]


def test_missing_official_years_accepts_any_iterable():
    assert missing_official_years(range(2030, 2033)) == [2031, 2032]


def test_a_custom_holiday_does_not_count_as_a_loaded_year(catalog_editor):
    create_holiday(catalog_editor, {"date": date(2031, 3, 3), "name": "Propio"})

    assert missing_official_years([2031]) == [2031]
