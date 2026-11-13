"""Pruebas del cálculo de los festivos oficiales de Colombia (SPEC 07, §3.3)."""

import ast
from datetime import date
from pathlib import Path

import pytest

from apps.parametros import holidays
from apps.parametros.holidays import (
    MAX_YEAR,
    MIN_YEAR,
    colombian_holidays,
    easter_sunday,
    next_monday,
)

# Pascua


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
        (2028, date(2028, 4, 16)),
        (2011, date(2011, 4, 24)),  # Pascua tardía
        (2008, date(2008, 3, 23)),  # Pascua temprana
        (2038, date(2038, 4, 25)),  # la más tardía posible
        (2100, date(2100, 3, 28)),
    ],
)
def test_easter_sunday(year, expected):
    assert easter_sunday(year) == expected


def test_easter_sunday_is_always_a_sunday():
    for year in range(MIN_YEAR, MAX_YEAR + 1):
        assert easter_sunday(year).isoweekday() == 7


# Al lunes


def test_next_monday_keeps_a_monday():
    assert next_monday(date(2026, 6, 29)) == date(2026, 6, 29)


def test_next_monday_moves_a_tuesday_to_the_following_monday():
    assert next_monday(date(2026, 1, 6)) == date(2026, 1, 12)


def test_next_monday_moves_a_sunday_to_the_next_day():
    assert next_monday(date(2026, 11, 1)) == date(2026, 11, 2)


# Festivos de un año


def test_holidays_2026():
    result = colombian_holidays(2026)

    assert [holiday.date for holiday in result] == [
        date(2026, 1, 1),
        date(2026, 1, 12),
        date(2026, 3, 23),
        date(2026, 4, 2),
        date(2026, 4, 3),
        date(2026, 5, 1),
        date(2026, 5, 18),
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 29),
        date(2026, 7, 20),
        date(2026, 8, 7),
        date(2026, 8, 17),
        date(2026, 10, 12),
        date(2026, 11, 2),
        date(2026, 11, 16),
        date(2026, 12, 8),
        date(2026, 12, 25),
    ]


def test_holiday_codes_and_names():
    by_code = {holiday.code: holiday for holiday in colombian_holidays(2026)}

    assert set(by_code) == {
        "ano_nuevo",
        "reyes_magos",
        "san_jose",
        "jueves_santo",
        "viernes_santo",
        "dia_trabajo",
        "ascension",
        "corpus_christi",
        "sagrado_corazon",
        "san_pedro_san_pablo",
        "independencia",
        "batalla_boyaca",
        "asuncion",
        "dia_raza",
        "todos_santos",
        "independencia_cartagena",
        "inmaculada_concepcion",
        "navidad",
    }
    assert by_code["batalla_boyaca"].name == "Batalla de Boyacá"
    assert by_code["reyes_magos"].date == date(2026, 1, 12)


@pytest.mark.parametrize("year", [MIN_YEAR, 2026, 2030, 2050, MAX_YEAR])
def test_every_year_has_18_holidays_sorted_by_date(year):
    result = colombian_holidays(year)

    assert len(result) == 18
    assert [h.date for h in result] == sorted(h.date for h in result)
    assert all(h.date.year == year for h in result)


def test_moved_and_easter_mondays_always_fall_on_monday():
    moved = {
        "reyes_magos",
        "san_jose",
        "ascension",
        "corpus_christi",
        "sagrado_corazon",
        "san_pedro_san_pablo",
        "asuncion",
        "dia_raza",
        "todos_santos",
        "independencia_cartagena",
    }
    for year in range(MIN_YEAR, MAX_YEAR + 1):
        for holiday in colombian_holidays(year):
            if holiday.code in moved:
                assert holiday.date.isoweekday() == 1, (year, holiday)


def test_two_holidays_on_the_same_day_keep_the_table_order():
    # En 2030 la Pascua es el 21 de abril: el Sagrado Corazón (P + 71) y
    # San Pedro y San Pablo (29 de junio, al lunes) caen el 1 de julio.
    same_day = [h for h in colombian_holidays(2030) if h.date == date(2030, 7, 1)]

    assert [h.code for h in same_day] == ["sagrado_corazon", "san_pedro_san_pablo"]


@pytest.mark.parametrize("year", [MIN_YEAR - 1, MAX_YEAR + 1])
def test_year_out_of_range(year):
    with pytest.raises(ValueError):
        colombian_holidays(year)


def test_module_does_not_import_django():
    tree = ast.parse(Path(holidays.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    assert not any(name.split(".")[0] == "django" for name in imported)
