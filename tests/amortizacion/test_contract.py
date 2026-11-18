"""El contrato del motor coincide con `apps.parametros` (SPEC 09, §3.2)."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from apps.amortizacion import types
from apps.amortizacion.errors import (
    AmortizationError,
    AmortizationInputError,
    RoundingError,
    UnsupportedMethodError,
)
from apps.parametros import models as parametros


@pytest.mark.parametrize(
    ("engine_enum", "parametros_enum"),
    [
        (types.InterestMethod, parametros.InterestMethod),
        (types.Periodicity, parametros.Periodicity),
        (types.RoundingMode, parametros.RoundingMode),
    ],
)
def test_option_values_match_parametros(engine_enum, parametros_enum):
    assert [member.value for member in engine_enum] == list(parametros_enum.values)


def test_days_per_period_covers_every_periodicity():
    assert set(types.DAYS_PER_PERIOD) == set(types.Periodicity)
    assert types.DAYS_PER_PERIOD[types.Periodicity.BIWEEKLY] == 15


def test_text_values_convert_to_enums():
    method = types.InterestMethod("flat_per_credit")

    assert method is types.InterestMethod.FLAT_PER_CREDIT


def _rule() -> types.RoundingRule:
    return types.RoundingRule(Decimal("50"), types.RoundingMode.HALF_UP)


@pytest.mark.parametrize(
    ("instance", "field"),
    [
        (_rule(), "multiple"),
        (
            types.ScheduleInput(
                principal=Decimal("100000"),
                rate=Decimal("10"),
                installments=20,
                method=types.InterestMethod.FLAT_PER_CREDIT,
                periodicity=types.Periodicity.DAILY,
                rounding=_rule(),
                money_precision=Decimal("1"),
            ),
            "principal",
        ),
        (
            types.Installment(
                number=1,
                opening_balance=Decimal("100"),
                principal=Decimal("100"),
                interest=Decimal("0"),
                payment=Decimal("100"),
                closing_balance=Decimal("0"),
            ),
            "payment",
        ),
        (
            types.Schedule(
                installments=(),
                regular_payment=Decimal("0"),
                total_principal=Decimal("0"),
                total_interest=Decimal("0"),
                total_payment=Decimal("0"),
            ),
            "total_payment",
        ),
    ],
)
def test_dataclasses_are_frozen(instance, field):
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field, Decimal("1"))


@pytest.mark.parametrize(
    "error_class", [AmortizationInputError, RoundingError, UnsupportedMethodError]
)
def test_errors_carry_code_and_field(error_class):
    error = error_class("El monto tiene que ser positivo.", code="x", field="principal")

    assert isinstance(error, AmortizationError)
    assert isinstance(error, ValueError)
    assert error.code == "x"
    assert error.field == "principal"
    assert error.message == str(error) == "El monto tiene que ser positivo."


def test_error_field_defaults_to_none():
    assert RoundingError("Sin solución.", code="zero_payment").field is None
