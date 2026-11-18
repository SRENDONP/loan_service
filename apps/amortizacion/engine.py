"""Punto de entrada del motor de amortización (SPEC 09, §3.9).

`build_schedule` es la única función que usan las otras apps, junto con los tipos
y los errores. No lee parámetros, no consulta la base de datos y no tiene estado.

Lógica pura: no importa Django ni otras apps del proyecto.
"""

from dataclasses import replace
from decimal import Decimal
from enum import StrEnum

from . import methods  # noqa: F401  (registra las estrategias)
from .errors import AmortizationInputError
from .registry import get_strategy
from .types import (
    InterestMethod,
    Periodicity,
    RoundingMode,
    RoundingRule,
    Schedule,
    ScheduleInput,
)

MAX_INSTALLMENTS = 999
MONEY_PRECISIONS = (Decimal("1"), Decimal("0.01"))


def build_schedule(data: ScheduleInput) -> Schedule:
    """Valida la entrada, la normaliza y devuelve la tabla del método."""
    normalized = validate_input(data)
    return get_strategy(normalized.method).build(normalized)


def validate_input(data: ScheduleInput) -> ScheduleInput:
    """Aplica las reglas de la §3.3 y devuelve la entrada con enums y precisión."""
    precision = _money_precision(data.money_precision)
    return replace(
        data,
        money_precision=precision,
        principal=_principal(data.principal, precision),
        rate=_rate(data.rate),
        installments=_installments(data.installments),
        method=_choice(InterestMethod, data.method, "method"),
        periodicity=_choice(Periodicity, data.periodicity, "periodicity"),
        rounding=_rounding(data.rounding, precision),
    )


def _error(message: str, code: str, field: str) -> AmortizationInputError:
    return AmortizationInputError(message, code=code, field=field)


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise _error("El valor tiene que ser un Decimal finito.", "invalid_type", field)
    return value


def _money_precision(value: object) -> Decimal:
    if isinstance(value, Decimal) and value.is_finite():
        for precision in MONEY_PRECISIONS:
            if value == precision:
                # Decimal("1.00") vale lo mismo que Decimal("1"), pero cambiaría
                # los decimales de la tabla: se usa siempre la forma canónica.
                return precision
    raise _error(
        "La precisión de la moneda tiene que ser 1 o 0.01.",
        "invalid_choice",
        "money_precision",
    )


def _principal(value: object, precision: Decimal) -> Decimal:
    principal = _decimal(value, "principal")
    if principal <= 0:
        raise _error("El monto tiene que ser mayor que 0.", "not_positive", "principal")
    if principal % precision != 0:
        raise _error(
            "El monto tiene más decimales que la moneda.", "precision", "principal"
        )
    return principal


def _rate(value: object) -> Decimal:
    rate = _decimal(value, "rate")
    if rate < 0:
        raise _error("La tasa no puede ser negativa.", "negative", "rate")
    return rate


def _installments(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _error(
            "El número de cuotas tiene que ser un entero.",
            "invalid_type",
            "installments",
        )
    if not 1 <= value <= MAX_INSTALLMENTS:
        raise _error(
            f"El número de cuotas tiene que estar entre 1 y {MAX_INSTALLMENTS}.",
            "out_of_range",
            "installments",
        )
    return value


def _choice[E: StrEnum](enum: type[E], value: object, field: str) -> E:
    try:
        return enum(value)
    except ValueError:
        raise _error(
            f"{value!r} no es una opción válida.", "invalid_choice", field
        ) from None


def _rounding(value: object, precision: Decimal) -> RoundingRule:
    if not isinstance(value, RoundingRule):
        raise _error(
            "El redondeo tiene que ser un RoundingRule.", "invalid_rounding", "rounding"
        )
    multiple = _decimal(value.multiple, "rounding.multiple")
    if multiple <= 0 or multiple % precision != 0:
        raise _error(
            "El múltiplo tiene que ser mayor que 0 y múltiplo de la precisión.",
            "invalid_rounding",
            "rounding.multiple",
        )
    mode = _choice(RoundingMode, value.mode, "rounding.mode")
    return RoundingRule(multiple=multiple, mode=mode)
