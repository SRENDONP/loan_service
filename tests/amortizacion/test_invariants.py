"""Malla de invariantes del motor (SPEC 09, §3.7 y paso 6 del plan).

Recorre todas las combinaciones de método, periodicidad, monto, cuotas, tasa,
múltiplo, modo y precisión. Cada caso cumple los invariantes o lanza
`RoundingError`; ningún otro resultado es aceptable.
"""

from decimal import Decimal
from itertools import product

import pytest

from apps.amortizacion.engine import build_schedule
from apps.amortizacion.errors import RoundingError
from apps.amortizacion.rounding import round_to_rule
from apps.amortizacion.types import (
    InterestMethod,
    Periodicity,
    RoundingMode,
    RoundingRule,
    Schedule,
    ScheduleInput,
)

D = Decimal

FLAT_METHODS = (
    InterestMethod.FLAT_PER_CREDIT,
    InterestMethod.FLAT_MONTHLY_PRORATED,
    InterestMethod.FLAT_PER_INSTALLMENT,
)
PRINCIPALS = (D("50"), D("1000"), D("100000"), D("12345678"))
INSTALLMENTS = (1, 2, 3, 7, 20, 30, 999)
RATES = (D("0"), D("0.5"), D("10"), D("100"))
MULTIPLES = (D("1"), D("10"), D("50"), D("100"), D("500"), D("1000"))
PRECISIONS = (D("1"), D("0.01"))


def assert_invariants(data: ScheduleInput, schedule: Schedule) -> None:
    rows = schedule.installments
    exponent = data.money_precision.as_tuple().exponent

    assert len(rows) == data.installments
    assert [row.number for row in rows] == list(range(1, data.installments + 1))

    # Capital, interés y cuotas cuadran exactamente.
    assert sum(row.principal for row in rows) == data.principal
    assert schedule.total_principal == data.principal
    assert sum(row.interest for row in rows) == schedule.total_interest
    assert sum(row.payment for row in rows) == schedule.total_payment
    assert schedule.total_payment == data.principal + schedule.total_interest

    # Saldos encadenados, que terminan exactamente en cero.
    assert rows[0].opening_balance == data.principal
    for previous, current in zip(rows, rows[1:], strict=False):
        assert current.opening_balance == previous.closing_balance
    assert rows[-1].closing_balance == 0

    for row in rows:
        assert row.principal >= 0
        assert row.interest >= 0
        assert row.payment > 0
        assert row.payment == row.principal + row.interest
        assert row.closing_balance == row.opening_balance - row.principal
        assert row.closing_balance >= 0
        for value in (
            row.opening_balance,
            row.principal,
            row.interest,
            row.payment,
            row.closing_balance,
        ):
            assert value.as_tuple().exponent >= exponent

    # Las cuotas regulares son iguales y múltiplo de la regla.
    regular = rows[:-1]
    assert all(row.payment == schedule.regular_payment for row in regular)
    if regular:
        multiple = data.rounding.multiple
        assert schedule.regular_payment % multiple == 0
    else:
        assert schedule.regular_payment == rows[0].payment


def _cases(method: InterestMethod, precision: Decimal):
    for periodicity, principal, count, rate, multiple, mode in product(
        Periodicity, PRINCIPALS, INSTALLMENTS, RATES, MULTIPLES, RoundingMode
    ):
        yield ScheduleInput(
            principal=principal,
            rate=rate,
            installments=count,
            method=method,
            periodicity=periodicity,
            rounding=RoundingRule(multiple, mode),
            money_precision=precision,
        )


@pytest.mark.parametrize("precision", PRECISIONS, ids=["pesos", "centavos"])
@pytest.mark.parametrize("method", FLAT_METHODS, ids=str)
def test_every_case_meets_the_invariants_or_raises(method, precision):
    built = 0
    rejected = 0
    for data in _cases(method, precision):
        try:
            schedule = build_schedule(data)
        except RoundingError:
            rejected += 1
            continue
        assert_invariants(data, schedule)
        built += 1

    # La malla tiene que ejercitar los dos caminos, y sobre todo el de la tabla.
    assert rejected > 0
    assert built > rejected


@pytest.mark.parametrize("method", FLAT_METHODS, ids=str)
def test_999_daily_installments(method):
    # Hacia abajo: con 999 cuotas, el capital regular es de unos 12.358 pesos, y
    # redondear la cuota hacia arriba más de 12 pesos ya paga de más (`overpaid`).
    data = ScheduleInput(
        principal=D("12345678"),
        rate=D("0.5"),
        installments=999,
        method=method,
        periodicity=Periodicity.DAILY,
        rounding=RoundingRule(D("50"), RoundingMode.DOWN),
        money_precision=D("1"),
    )

    schedule = build_schedule(data)

    assert_invariants(data, schedule)
    assert len(schedule.installments) == 999


def test_assert_invariants_detects_a_broken_schedule():
    data = ScheduleInput(
        principal=D("1000"),
        rate=D("0"),
        installments=2,
        method=InterestMethod.FLAT_PER_CREDIT,
        periodicity=Periodicity.DAILY,
        rounding=RoundingRule(D("1"), RoundingMode.HALF_UP),
        money_precision=D("1"),
    )
    schedule = build_schedule(data)
    broken = Schedule(
        installments=schedule.installments[:1],
        regular_payment=schedule.regular_payment,
        total_principal=schedule.total_principal,
        total_interest=schedule.total_interest,
        total_payment=schedule.total_payment,
    )

    with pytest.raises(AssertionError):
        assert_invariants(data, broken)


def test_regular_payment_is_the_rounded_share():
    # Comprobación independiente del reparto: la cuota regular es (P + I) / n
    # redondeada a la regla, recalculada aquí sin pasar por el motor.
    data = ScheduleInput(
        principal=D("12345678"),
        rate=D("10"),
        installments=30,
        method=InterestMethod.FLAT_PER_CREDIT,
        periodicity=Periodicity.DAILY,
        rounding=RoundingRule(D("100"), RoundingMode.UP),
        money_precision=D("1"),
    )

    schedule = build_schedule(data)

    expected = round_to_rule(D("13580245.8") / 30, data.rounding)
    assert schedule.total_interest == D("1234568")
    assert schedule.regular_payment == expected
