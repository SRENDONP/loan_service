"""Contrato de entrada y salida del motor de amortización (SPEC 09, §3.2 a §3.4).

Lógica pura: no importa Django ni otras apps del proyecto. Los valores de las
opciones son los mismos de `apps.parametros`, y `tests/amortizacion/test_contract.py`
los compara.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class InterestMethod(StrEnum):
    FLAT_PER_CREDIT = "flat_per_credit"
    FLAT_MONTHLY_PRORATED = "flat_monthly_prorated"
    FLAT_PER_INSTALLMENT = "flat_per_installment"
    FRENCH = "french"
    GERMAN = "german"
    DECLINING_BALANCE = "declining_balance"


class Periodicity(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class RoundingMode(StrEnum):
    HALF_UP = "half_up"
    UP = "up"
    DOWN = "down"


# Meses de 30 días: lo usa solo el plano mensual prorrateado (§3.6).
DAYS_PER_PERIOD: dict[Periodicity, int] = {
    Periodicity.DAILY: 1,
    Periodicity.WEEKLY: 7,
    Periodicity.BIWEEKLY: 15,
    Periodicity.MONTHLY: 30,
}


@dataclass(frozen=True, slots=True)
class RoundingRule:
    """Múltiplo y modo con que se redondean las cuotas regulares."""

    multiple: Decimal  # 1, 10, 50, 100, 500 o 1000
    mode: RoundingMode


@dataclass(frozen=True, slots=True)
class ScheduleInput:
    """Parámetros del cálculo. La tasa está en la unidad que fija el método."""

    principal: Decimal  # monto del crédito
    rate: Decimal  # porcentaje en la unidad del método: 10 es 10 %
    installments: int  # número de cuotas
    method: InterestMethod
    periodicity: Periodicity
    rounding: RoundingRule
    money_precision: Decimal  # Decimal("1") o Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Installment:
    """Una fila de la tabla. Los saldos son saldos de capital (§9.3)."""

    number: int  # 1..n
    opening_balance: Decimal  # saldo de capital antes de la cuota
    principal: Decimal  # abono a capital
    interest: Decimal
    payment: Decimal  # principal + interest
    closing_balance: Decimal  # opening_balance - principal


@dataclass(frozen=True, slots=True)
class Schedule:
    """La tabla de amortización completa y sus totales."""

    installments: tuple[Installment, ...]
    regular_payment: Decimal  # cuotas 1 a n-1 (con 1 cuota, el de esa cuota)
    total_principal: Decimal  # igual al monto
    total_interest: Decimal
    total_payment: Decimal  # total_principal + total_interest
