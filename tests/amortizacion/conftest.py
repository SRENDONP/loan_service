"""Ayudas de las pruebas del motor (SPEC 09)."""

from dataclasses import replace
from decimal import Decimal
from typing import Any

from apps.amortizacion.types import (
    InterestMethod,
    Periodicity,
    RoundingMode,
    RoundingRule,
    ScheduleInput,
)

BASE_INPUT = ScheduleInput(
    principal=Decimal("100000"),
    rate=Decimal("10"),
    installments=20,
    method=InterestMethod.FLAT_PER_CREDIT,
    periodicity=Periodicity.DAILY,
    rounding=RoundingRule(Decimal("50"), RoundingMode.HALF_UP),
    money_precision=Decimal("1"),
)


def make_input(**overrides: Any) -> ScheduleInput:
    """El crédito de la hoja (100.000, 10 %, 20 cuotas diarias) con cambios.

    `multiple` y `mode` cambian la regla de redondeo sin armarla a mano.
    """
    multiple = overrides.pop("multiple", None)
    mode = overrides.pop("mode", None)
    if multiple is not None or mode is not None:
        overrides["rounding"] = RoundingRule(
            Decimal(multiple) if multiple is not None else BASE_INPUT.rounding.multiple,
            mode if mode is not None else BASE_INPUT.rounding.mode,
        )
    return replace(BASE_INPUT, **overrides)
