"""Pruebas del comando `cargar_festivos` (SPEC 07, §3.7)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent, AuditSource
from apps.parametros.holidays import colombian_holidays
from apps.parametros.models import Holiday, HolidayOrigin

pytestmark = pytest.mark.django_db


def run(*years: str) -> str:
    out = StringIO()
    call_command("cargar_festivos", *years, stdout=out)
    return out.getvalue()


def loaded_events():
    return AuditEvent.objects.filter(action=AuditAction.HOLIDAYS_LOADED)


def test_loads_one_year():
    output = run("2031")

    assert output.splitlines() == ["2031: 18 festivos creados."]
    assert Holiday.objects.filter(official_year=2031).count() == 18


def test_loads_several_years_with_one_line_each():
    output = run("2031", "2032")

    assert output.splitlines() == [
        "2031: 18 festivos creados.",
        "2032: 18 festivos creados.",
    ]
    assert Holiday.objects.filter(official_year__in=[2031, 2032]).count() == 36


def test_a_loaded_year_reports_nothing_missing():
    output = run("2026")

    assert output.splitlines() == ["2026: no faltaba ningún festivo."]
    assert not loaded_events().exists()


def test_second_run_creates_nothing():
    run("2031")

    output = run("2031")

    assert output.splitlines() == ["2031: no faltaba ningún festivo."]
    assert Holiday.objects.filter(official_year=2031).count() == 18
    assert loaded_events().count() == 1


def test_a_single_missing_holiday_uses_the_singular():
    Holiday.objects.bulk_create(
        [
            Holiday(
                date=holiday.date,
                name=holiday.name,
                origin=HolidayOrigin.OFFICIAL,
                official_code=holiday.code,
                official_year=2031,
            )
            for holiday in colombian_holidays(2031)
            if holiday.code != "navidad"
        ]
    )

    assert run("2031").splitlines() == ["2031: 1 festivo creado."]


def test_repeated_years_are_loaded_once():
    output = run("2031", "2031")

    assert output.splitlines() == ["2031: 18 festivos creados."]


def test_an_invalid_year_fails_without_loading_any():
    with pytest.raises(CommandError) as excinfo:
        run("2031", "1980")

    assert "1980" in str(excinfo.value)
    assert not Holiday.objects.filter(official_year=2031).exists()
    assert not loaded_events().exists()


def test_a_year_after_the_range_fails():
    with pytest.raises(CommandError):
        run("2101")


def test_a_non_numeric_year_fails():
    with pytest.raises(CommandError):
        run("abc")


def test_without_years_fails():
    with pytest.raises(CommandError):
        run()


def test_the_record_has_command_source_no_actor_and_extra():
    run("2031", "2032")

    first, second = loaded_events().order_by("pk")
    assert first.source == AuditSource.COMMAND
    assert first.actor is None
    assert first.ip_address is None
    assert first.extra == {"year": 2031, "created": 18}
    assert second.extra == {"year": 2032, "created": 18}
