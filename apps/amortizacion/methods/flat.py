"""Métodos de interés plano del motor (SPEC 09, §3.6 y §3.7).

El interés total se calcula sobre el monto original y se reparte en cuotas
iguales. Los tres métodos comparten el reparto: solo cambia el interés total.

Lógica pura: no importa Django ni otras apps del proyecto.
"""

from decimal import Decimal, localcontext

from ..errors import RoundingError
from ..registry import register
from ..rounding import PRECISION_DIGITS, quantize_money, round_to_rule
from ..types import (
    DAYS_PER_PERIOD,
    Installment,
    InterestMethod,
    RoundingMode,
    Schedule,
    ScheduleInput,
)

_HUNDRED = Decimal("100")
_DAYS_PER_MONTH = Decimal("30")


class FlatStrategy:
    """Base de los métodos planos: el interés total y el reparto común."""

    def raw_interest(self, data: ScheduleInput) -> Decimal:
        """El interés total sin redondear. Cada método lo define."""
        raise NotImplementedError

    def total_interest(self, data: ScheduleInput) -> Decimal:
        """El interés total, redondeado una sola vez a la precisión de la moneda."""
        with localcontext() as context:
            context.prec = PRECISION_DIGITS
            raw = self.raw_interest(data)
        return quantize_money(raw, data.money_precision, RoundingMode.HALF_UP)

    def build(self, data: ScheduleInput) -> Schedule:
        return distribute(data, self.total_interest(data))


@register(InterestMethod.FLAT_PER_CREDIT)
class FlatPerCreditStrategy(FlatStrategy):
    """Un porcentaje sobre el capital por todo el crédito: `P × r / 100`."""

    def raw_interest(self, data: ScheduleInput) -> Decimal:
        return data.principal * data.rate / _HUNDRED


@register(InterestMethod.FLAT_MONTHLY_PRORATED)
class FlatMonthlyProratedStrategy(FlatStrategy):
    """Tasa mensual por los meses del plazo, con meses de 30 días.

    `P × r / 100 × n × días del periodo / 30`. Las multiplicaciones van antes de la
    división, para que 20 cuotas diarias sean exactamente 20/30 de mes.
    """

    def raw_interest(self, data: ScheduleInput) -> Decimal:
        days = DAYS_PER_PERIOD[data.periodicity]
        numerator = data.principal * data.rate * data.installments * days
        return numerator / (_HUNDRED * _DAYS_PER_MONTH)


@register(InterestMethod.FLAT_PER_INSTALLMENT)
class FlatPerInstallmentStrategy(FlatStrategy):
    """Tasa por periodo por el número de cuotas: `P × r / 100 × n`."""

    def raw_interest(self, data: ScheduleInput) -> Decimal:
        return data.principal * data.rate * data.installments / _HUNDRED


def _rounding_error(message: str, code: str) -> RoundingError:
    return RoundingError(message, code=code)


def distribute(data: ScheduleInput, total_interest: Decimal) -> Schedule:
    """Reparte el monto y el interés total en cuotas (§3.7).

    Las cuotas regulares se redondean a la regla, el interés de cada una se trunca
    hacia abajo y la última cuota absorbe todas las diferencias.
    """
    principal = data.principal
    count = data.installments
    precision = data.money_precision

    def money(value: Decimal, mode: RoundingMode = RoundingMode.HALF_UP) -> Decimal:
        return quantize_money(value, precision, mode)

    if count == 1:
        rows = [(money(principal), money(total_interest))]
    else:
        with localcontext() as context:
            context.prec = PRECISION_DIGITS
            raw_payment = (principal + total_interest) / count
            raw_interest = total_interest / count

        payment = money(round_to_rule(raw_payment, data.rounding))
        if payment.is_zero():
            raise _rounding_error(
                "Con este redondeo, la cuota queda en 0.", "zero_payment"
            )

        interest = money(raw_interest, RoundingMode.DOWN)
        regular_principal = payment - interest
        if regular_principal < 0:
            raise _rounding_error(
                "Con este redondeo, la cuota no alcanza para su interés.",
                "negative_principal",
            )

        last_principal = principal - (count - 1) * regular_principal
        if last_principal < 0:
            raise _rounding_error(
                "Con este redondeo, las cuotas pagan más que el monto.", "overpaid"
            )

        last_interest = total_interest - (count - 1) * interest
        if (last_principal + last_interest).is_zero():
            raise _rounding_error(
                "Con este redondeo, la última cuota queda en 0.", "zero_last_payment"
            )

        rows = [(regular_principal, interest)] * (count - 1)
        rows.append((money(last_principal), money(last_interest)))

    installments: list[Installment] = []
    balance = money(principal)
    for number, (row_principal, row_interest) in enumerate(rows, start=1):
        closing = balance - row_principal
        installments.append(
            Installment(
                number=number,
                opening_balance=balance,
                principal=row_principal,
                interest=row_interest,
                payment=row_principal + row_interest,
                closing_balance=closing,
            )
        )
        balance = closing

    return Schedule(
        installments=tuple(installments),
        regular_payment=installments[0].payment,
        total_principal=money(principal),
        total_interest=money(total_interest),
        total_payment=money(principal + total_interest),
    )
