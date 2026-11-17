"""Redondeo del motor de amortización (SPEC 09, §3.7).

Lógica pura: no importa Django ni otras apps del proyecto.
"""

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal, localcontext

from .types import RoundingMode, RoundingRule

# 28 dígitos alcanzan de sobra para montos de 14 dígitos y tasas de 4 decimales.
PRECISION_DIGITS = 28

DECIMAL_ROUNDING: dict[RoundingMode, str] = {
    RoundingMode.HALF_UP: ROUND_HALF_UP,
    RoundingMode.UP: ROUND_CEILING,
    RoundingMode.DOWN: ROUND_FLOOR,
}

_ONE = Decimal("1")


def _without_negative_zero(value: Decimal) -> Decimal:
    # ROUND_CEILING sobre un negativo pequeño da "-0"; en el motor un cero es cero.
    return abs(value) if value.is_zero() else value


def round_to_rule(value: Decimal, rule: RoundingRule) -> Decimal:
    """Redondea `value` a un múltiplo de `rule.multiple`, en el modo de la regla."""
    with localcontext() as context:
        context.prec = PRECISION_DIGITS
        units = (value / rule.multiple).quantize(
            _ONE, rounding=DECIMAL_ROUNDING[rule.mode]
        )
        return _without_negative_zero(units * rule.multiple)


def quantize_money(value: Decimal, precision: Decimal, mode: RoundingMode) -> Decimal:
    """Deja `value` a la precisión de la moneda (`1` o `0.01`), en el modo dado."""
    with localcontext() as context:
        context.prec = PRECISION_DIGITS
        rounded = value.quantize(precision, rounding=DECIMAL_ROUNDING[mode])
        return _without_negative_zero(rounded)
