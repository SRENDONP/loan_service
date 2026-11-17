"""Validación de la entrada del motor (SPEC 09, §3.3)."""

from decimal import Decimal

import pytest

from apps.amortizacion.engine import build_schedule, validate_input
from apps.amortizacion.errors import AmortizationInputError, UnsupportedMethodError
from apps.amortizacion.registry import registered_methods
from apps.amortizacion.types import (
    InterestMethod,
    Periodicity,
    RoundingMode,
    RoundingRule,
)

from .conftest import make_input

D = Decimal


@pytest.mark.parametrize(
    ("overrides", "field", "code"),
    [
        # Monto
        ({"principal": 100000}, "principal", "invalid_type"),
        ({"principal": 100000.0}, "principal", "invalid_type"),
        ({"principal": "100000"}, "principal", "invalid_type"),
        ({"principal": D("NaN")}, "principal", "invalid_type"),
        ({"principal": D("Infinity")}, "principal", "invalid_type"),
        ({"principal": D("0")}, "principal", "not_positive"),
        ({"principal": D("-1")}, "principal", "not_positive"),
        ({"principal": D("100000.50")}, "principal", "precision"),
        (
            {"principal": D("100000.005"), "money_precision": D("0.01")},
            "principal",
            "precision",
        ),
        # Tasa
        ({"rate": 10.0}, "rate", "invalid_type"),
        ({"rate": 10}, "rate", "invalid_type"),
        ({"rate": D("-0.0001")}, "rate", "negative"),
        # Cuotas
        ({"installments": 20.0}, "installments", "invalid_type"),
        ({"installments": True}, "installments", "invalid_type"),
        ({"installments": "20"}, "installments", "invalid_type"),
        ({"installments": 0}, "installments", "out_of_range"),
        ({"installments": 1000}, "installments", "out_of_range"),
        # Opciones
        ({"method": "flat"}, "method", "invalid_choice"),
        ({"method": None}, "method", "invalid_choice"),
        ({"periodicity": "yearly"}, "periodicity", "invalid_choice"),
        ({"money_precision": D("0.1")}, "money_precision", "invalid_choice"),
        ({"money_precision": D("0.001")}, "money_precision", "invalid_choice"),
        ({"money_precision": 1}, "money_precision", "invalid_choice"),
        ({"money_precision": D("NaN")}, "money_precision", "invalid_choice"),
        # Redondeo
        ({"rounding": None}, "rounding", "invalid_rounding"),
        ({"multiple": D("0")}, "rounding.multiple", "invalid_rounding"),
        ({"multiple": D("-50")}, "rounding.multiple", "invalid_rounding"),
        ({"multiple": D("0.5")}, "rounding.multiple", "invalid_rounding"),
        (
            {"rounding": RoundingRule(D("50"), "nearest")},
            "rounding.mode",
            "invalid_choice",
        ),
    ],
)
def test_invalid_input_raises_with_code_and_field(overrides, field, code):
    with pytest.raises(AmortizationInputError) as excinfo:
        build_schedule(make_input(**overrides))

    assert excinfo.value.field == field
    assert excinfo.value.code == code
    assert excinfo.value.message


@pytest.mark.parametrize("field", ["principal", "rate", "multiple"])
def test_floats_never_enter_the_engine(field):
    overrides = {field: 50.0}
    if field == "multiple":
        overrides = {"rounding": RoundingRule(50.0, RoundingMode.HALF_UP)}

    with pytest.raises(AmortizationInputError) as excinfo:
        validate_input(make_input(**overrides))

    assert excinfo.value.code == "invalid_type"


@pytest.mark.parametrize(
    "overrides",
    [
        {"rate": D("0")},
        {"installments": 1},
        {"installments": 999},
        {"principal": D("100000.50"), "money_precision": D("0.01")},
        {"multiple": D("1")},
        {"multiple": D("1000"), "mode": RoundingMode.DOWN},
    ],
)
def test_valid_edge_values_pass(overrides):
    data = make_input(**overrides)

    assert validate_input(data) == data


def test_text_values_are_normalized_to_enums():
    data = make_input(
        method="flat_monthly_prorated",
        periodicity="weekly",
        rounding=RoundingRule(D("100"), "up"),
    )

    normalized = validate_input(data)

    assert normalized.method is InterestMethod.FLAT_MONTHLY_PRORATED
    assert normalized.periodicity is Periodicity.WEEKLY
    assert normalized.rounding == RoundingRule(D("100"), RoundingMode.UP)
    assert normalized.rounding.mode is RoundingMode.UP


@pytest.mark.parametrize(
    ("given", "expected_exponent"), [("1.00", 0), ("1", 0), ("0.010", -2)]
)
def test_money_precision_is_made_canonical(given, expected_exponent):
    normalized = validate_input(make_input(money_precision=D(given)))

    assert normalized.money_precision.as_tuple().exponent == expected_exponent


@pytest.mark.parametrize(
    "method", sorted(set(InterestMethod) - registered_methods()), ids=str
)
def test_unregistered_methods_raise_unsupported(method):
    with pytest.raises(UnsupportedMethodError) as excinfo:
        build_schedule(make_input(method=method))

    assert excinfo.value.code == "unsupported_method"
    assert excinfo.value.field == "method"
