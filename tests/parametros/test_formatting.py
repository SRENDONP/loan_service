"""Pruebas del formato de dinero y fechas (SPEC 06, §3.6)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.template import engines

from apps.parametros.formatting import (
    format_date,
    format_datetime,
    format_money,
    format_percent,
)
from apps.parametros.models import DateFormat

pytestmark = pytest.mark.django_db

DECEMBER_31 = date(2026, 12, 31)
# 19:05 UTC son las 14:05 en America/Bogota (UTC-5, sin horario de verano).
DECEMBER_31_UTC = datetime(2026, 12, 31, 19, 5, tzinfo=UTC)


def render(source: str, **context) -> str:
    template = engines["django"].from_string("{% load formato %}" + source)
    return template.render(context)


# Dinero


def test_money_with_default_settings():
    assert format_money(Decimal("1234567.5")) == "$1.234.568"


def test_money_with_two_decimals(global_settings):
    global_settings.currency_decimals = 2
    global_settings.save()

    assert format_money(Decimal("1234567.5")) == "$1.234.567,50"


def test_money_negative():
    assert format_money(Decimal("-1500")) == "-$1.500"


def test_money_rounds_half_up_for_display():
    assert format_money(Decimal("0.5")) == "$1"
    assert format_money(Decimal("-0.5")) == "-$1"
    assert format_money(Decimal("2.4")) == "$2"


def test_money_accepts_int_and_small_values():
    assert format_money(0) == "$0"
    assert format_money(999) == "$999"
    assert format_money(1000) == "$1.000"


def test_money_none_is_empty():
    assert format_money(None) == ""


@pytest.mark.parametrize("value", [1.5, "1500", True])
def test_money_rejects_float_and_other_types(value):
    with pytest.raises(TypeError):
        format_money(value)


def test_money_uses_the_configured_symbol(global_settings):
    global_settings.currency_symbol = "COP$"
    global_settings.save()

    assert format_money(Decimal("1500")) == "COP$1.500"


# Fechas


@pytest.mark.parametrize(
    ("date_format", "expected_date"),
    [
        (DateFormat.DMY_SLASH, "31/12/2026"),
        (DateFormat.DMY_DASH, "31-12-2026"),
        (DateFormat.ISO, "2026-12-31"),
        (DateFormat.LONG, "31 de diciembre de 2026"),
    ],
)
def test_date_and_datetime_follow_each_format(
    global_settings, date_format, expected_date
):
    global_settings.date_format = date_format
    global_settings.save()

    assert format_date(DECEMBER_31) == expected_date
    assert format_datetime(DECEMBER_31_UTC) == f"{expected_date} 14:05"


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 1, 5), "5 de enero de 2026"),
        (date(2026, 9, 15), "15 de septiembre de 2026"),
    ],
)
def test_long_format_writes_the_month_in_lowercase(global_settings, day, expected):
    # Django traduce los meses con mayúscula; en español van en minúscula.
    global_settings.date_format = DateFormat.LONG
    global_settings.save()

    assert format_date(day) == expected


def test_datetime_uses_bogota_local_time():
    # 03:00 UTC del 1 de enero son las 22:00 del 31 de diciembre en Bogotá.
    value = datetime(2027, 1, 1, 3, 0, tzinfo=UTC)

    assert format_datetime(value) == "31/12/2026 22:00"
    assert format_date(value) == "31/12/2026"


def test_naive_datetime_is_not_shifted():
    assert format_datetime(datetime(2026, 12, 31, 14, 5)) == "31/12/2026 14:05"


def test_dates_none_are_empty():
    assert format_date(None) == ""
    assert format_datetime(None) == ""


# Filtros


def test_template_filters():
    html = render(
        "{{ amount|moneda }}|{{ day|fecha }}|{{ moment|fecha_hora }}"
        "|{{ empty|moneda }}",
        amount=Decimal("1234567.5"),
        day=DECEMBER_31,
        moment=DECEMBER_31_UTC,
        empty=None,
    )

    assert html == "$1.234.568|31/12/2026|31/12/2026 14:05|"


# Porcentajes (SPEC 08)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("25.0200"), "25,02"),
        (Decimal("10.0000"), "10"),
        (Decimal("100"), "100"),
        (Decimal("0.5000"), "0,5"),
        (Decimal("0"), "0"),
        (Decimal("9999.9999"), "9.999,9999"),
        (5, "5"),
    ],
)
def test_format_percent_drops_trailing_zeros(value, expected):
    assert format_percent(value) == expected


def test_format_percent_of_none_is_empty():
    assert format_percent(None) == ""


@pytest.mark.parametrize("value", [25.02, "25", True])
def test_format_percent_rejects_other_types(value):
    with pytest.raises(TypeError):
        format_percent(value)


def test_porcentaje_filter():
    template = engines["django"].from_string(
        "{% load formato %}{{ value|porcentaje }} % EA"
    )

    assert template.render({"value": Decimal("25.0200")}) == "25,02 % EA"
