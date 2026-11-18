"""Redondeo del motor (SPEC 09, §3.7)."""

from decimal import Decimal

import pytest

from apps.amortizacion.rounding import DECIMAL_ROUNDING, quantize_money, round_to_rule
from apps.amortizacion.types import RoundingMode, RoundingRule

D = Decimal
HALF_UP = RoundingMode.HALF_UP
UP = RoundingMode.UP
DOWN = RoundingMode.DOWN


def test_every_mode_has_a_decimal_rounding():
    assert set(DECIMAL_ROUNDING) == set(RoundingMode)


@pytest.mark.parametrize(
    ("value", "multiple", "mode", "expected"),
    [
        # Valor exacto: ningún modo lo cambia.
        ("5500", "50", HALF_UP, "5500"),
        ("5500", "50", UP, "5500"),
        ("5500", "50", DOWN, "5500"),
        # A mitad de camino.
        ("5525", "50", HALF_UP, "5550"),
        ("5525", "50", UP, "5550"),
        ("5525", "50", DOWN, "5500"),
        ("5500", "1000", HALF_UP, "6000"),
        # Justo por debajo y por encima de la mitad.
        ("5524.99", "50", HALF_UP, "5500"),
        ("5525.01", "50", DOWN, "5500"),
        ("5500.01", "50", UP, "5550"),
        # Con decimales y el múltiplo de 1.
        ("5333.35", "50", HALF_UP, "5350"),
        ("5333.35", "1", HALF_UP, "5333"),
        ("5333.5", "1", HALF_UP, "5334"),
        ("5333.01", "1", UP, "5334"),
        ("5333.99", "1", DOWN, "5333"),
        # Valores que quedan en cero.
        ("5", "50", HALF_UP, "0"),
        ("24.99", "50", HALF_UP, "0"),
        ("25", "50", HALF_UP, "50"),
        ("49.99", "50", DOWN, "0"),
        ("0.01", "1000", UP, "1000"),
        ("0", "50", UP, "0"),
    ],
)
def test_round_to_rule(value, multiple, mode, expected):
    assert round_to_rule(D(value), RoundingRule(D(multiple), mode)) == D(expected)


@pytest.mark.parametrize("mode", [HALF_UP, UP])
def test_round_to_rule_never_returns_negative_zero(mode):
    assert str(round_to_rule(D("-0.4"), RoundingRule(D("1"), mode))) == "0"


@pytest.mark.parametrize("mode", list(RoundingMode))
def test_round_to_rule_keeps_zero_unsigned(mode):
    assert not round_to_rule(D("0"), RoundingRule(D("50"), mode)).is_signed()


@pytest.mark.parametrize(
    ("value", "precision", "mode", "expected"),
    [
        ("6666.666666", "1", HALF_UP, "6667"),
        ("6666.666666", "0.01", HALF_UP, "6666.67"),
        ("333.35", "1", DOWN, "333"),
        ("333.3335", "0.01", DOWN, "333.33"),
        ("333.335", "0.01", HALF_UP, "333.34"),
        ("333.331", "0.01", UP, "333.34"),
        ("100000", "1", HALF_UP, "100000"),
        ("0.4", "1", HALF_UP, "0"),
    ],
)
def test_quantize_money(value, precision, mode, expected):
    result = quantize_money(D(value), D(precision), mode)

    assert result == D(expected)
    assert result.as_tuple().exponent == D(precision).as_tuple().exponent


def test_quantize_money_never_returns_negative_zero():
    assert str(quantize_money(D("-0.4"), D("1"), UP)) == "0"
