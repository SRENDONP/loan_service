"""Métodos de interés plano (SPEC 09, §3.6, §3.7 y §5)."""

from decimal import Decimal

import pytest

from apps.amortizacion.engine import build_schedule
from apps.amortizacion.errors import RoundingError
from apps.amortizacion.methods.flat import FlatStrategy
from apps.amortizacion.registry import registered_methods
from apps.amortizacion.types import InterestMethod, RoundingMode, Schedule

from .conftest import make_input

D = Decimal
HALF_UP = RoundingMode.HALF_UP
UP = RoundingMode.UP
DOWN = RoundingMode.DOWN
FLAT = InterestMethod.FLAT_PER_CREDIT


def rows(schedule: Schedule) -> list[tuple[Decimal, Decimal, Decimal]]:
    """(interés, capital, cuota) de cada fila."""
    return [(row.interest, row.principal, row.payment) for row in schedule.installments]


def assert_balances_chain(schedule: Schedule, principal: Decimal) -> None:
    balance = principal
    for row in schedule.installments:
        assert row.opening_balance == balance
        assert row.closing_balance == row.opening_balance - row.principal
        balance = row.closing_balance
    assert balance == 0


# Registro


def test_flat_per_credit_is_registered():
    assert FLAT in registered_methods()


def test_base_strategy_requires_raw_interest():
    with pytest.raises(NotImplementedError):
        FlatStrategy().raw_interest(make_input())


# Plano fijo por crédito


def test_flat_per_credit_sheet_example():
    schedule = build_schedule(make_input(method=FLAT))

    assert schedule.total_interest == D("10000")
    assert rows(schedule) == [(D("500"), D("5000"), D("5500"))] * 20
    assert schedule.regular_payment == D("5500")
    assert schedule.total_principal == D("100000")
    assert schedule.total_payment == D("110000")
    assert [row.number for row in schedule.installments] == list(range(1, 21))
    assert_balances_chain(schedule, D("100000"))


def test_flat_per_credit_text_method_gives_the_same_table():
    assert build_schedule(make_input(method="flat_per_credit")) == build_schedule(
        make_input(method=FLAT)
    )


def test_flat_per_credit_multiple_1000_down():
    schedule = build_schedule(make_input(multiple="1000", mode=DOWN))

    assert rows(schedule)[:19] == [(D("500"), D("4500"), D("5000"))] * 19
    assert rows(schedule)[19] == (D("500"), D("14500"), D("15000"))
    assert schedule.regular_payment == D("5000")
    assert_balances_chain(schedule, D("100000"))


@pytest.mark.parametrize(
    ("multiple", "mode"),
    [("50", HALF_UP), ("50", UP), ("50", DOWN), ("1000", UP), ("1000", HALF_UP)],
)
def test_one_installment_ignores_the_multiple(multiple, mode):
    schedule = build_schedule(make_input(installments=1, multiple=multiple, mode=mode))

    assert rows(schedule) == [(D("10000"), D("100000"), D("110000"))]
    assert schedule.regular_payment == D("110000")
    assert_balances_chain(schedule, D("100000"))


def test_zero_rate_three_installments():
    schedule = build_schedule(make_input(rate=D("0"), installments=3))

    assert schedule.total_interest == D("0")
    assert rows(schedule) == [
        (D("0"), D("33350"), D("33350")),
        (D("0"), D("33350"), D("33350")),
        (D("0"), D("33300"), D("33300")),
    ]
    assert_balances_chain(schedule, D("100000"))


def test_small_amount_with_multiple_of_1():
    schedule = build_schedule(make_input(principal=D("100"), rate=D("0"), multiple="1"))

    assert rows(schedule) == [(D("0"), D("5"), D("5"))] * 20


def test_values_keep_the_money_precision():
    schedule = build_schedule(
        make_input(principal=D("100000.00"), money_precision=D("0.01"), rate=D("7"))
    )

    for row in schedule.installments:
        for value in (row.opening_balance, row.principal, row.interest, row.payment):
            assert value.as_tuple().exponent == -2
    assert schedule.total_interest == D("7000.00")


# Redondeo sin solución


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"principal": D("100"), "rate": D("0")}, "zero_payment"),
        ({"multiple": "1000", "mode": UP}, "overpaid"),
        ({"multiple": "1000", "mode": HALF_UP}, "overpaid"),
        (
            {
                "principal": D("1000"),
                "rate": D("0"),
                "installments": 3,
                "multiple": "500",
                "mode": UP,
            },
            "zero_last_payment",
        ),
        (
            {
                "principal": D("10"),
                "rate": D("1100"),
                "installments": 2,
                "multiple": "50",
                "mode": DOWN,
            },
            "negative_principal",
        ),
    ],
)
def test_unsolvable_rounding_raises(overrides, code):
    with pytest.raises(RoundingError) as excinfo:
        build_schedule(make_input(method=FLAT, **overrides))

    assert excinfo.value.code == code
    assert excinfo.value.field is None
    assert excinfo.value.message


def test_regular_principal_of_zero_is_allowed():
    # 10 al 1.000 % en 2 cuotas: interés 100 y (10 + 100) / 2 = 55, que hacia
    # abajo a 50 deja una cuota de 50 con 50 de interés y 0 de capital. Todo el
    # capital queda en la última.
    schedule = build_schedule(
        make_input(
            principal=D("10"),
            rate=D("1000"),
            installments=2,
            multiple="50",
            mode=DOWN,
        )
    )

    assert rows(schedule) == [(D("50"), D("0"), D("50")), (D("50"), D("10"), D("60"))]
    assert_balances_chain(schedule, D("10"))


def test_same_input_gives_equal_schedules():
    assert build_schedule(make_input()) == build_schedule(make_input())


# Plano mensual prorrateado

PRORATED = InterestMethod.FLAT_MONTHLY_PRORATED
PER_INSTALLMENT = InterestMethod.FLAT_PER_INSTALLMENT


def test_three_flat_methods_are_registered():
    assert registered_methods() == frozenset({FLAT, PRORATED, PER_INSTALLMENT})


def test_prorated_daily_sheet_example():
    schedule = build_schedule(make_input(method=PRORATED))

    assert schedule.total_interest == D("6667")
    assert rows(schedule)[:19] == [(D("333"), D("5017"), D("5350"))] * 19
    assert rows(schedule)[19] == (D("340"), D("4677"), D("5017"))
    assert schedule.regular_payment == D("5350")
    assert schedule.total_principal == D("100000")
    assert schedule.total_payment == D("106667")
    assert_balances_chain(schedule, D("100000"))


def test_prorated_daily_with_cents():
    schedule = build_schedule(make_input(method=PRORATED, money_precision=D("0.01")))

    assert schedule.total_interest == D("6666.67")
    assert rows(schedule)[:19] == [(D("333.33"), D("5016.67"), D("5350.00"))] * 19
    assert rows(schedule)[19] == (D("333.40"), D("4683.27"), D("5016.67"))
    assert schedule.total_payment == D("106666.67")
    assert_balances_chain(schedule, D("100000"))


def test_prorated_weekly():
    schedule = build_schedule(
        make_input(method=PRORATED, periodicity="weekly", installments=8)
    )

    assert schedule.total_interest == D("18667")
    assert rows(schedule)[:7] == [(D("2333"), D("12517"), D("14850"))] * 7
    assert rows(schedule)[7] == (D("2336"), D("12381"), D("14717"))
    assert_balances_chain(schedule, D("100000"))


@pytest.mark.parametrize(
    ("periodicity", "installments"), [("biweekly", 6), ("monthly", 3)]
)
def test_prorated_three_months_give_the_same_interest(periodicity, installments):
    schedule = build_schedule(
        make_input(method=PRORATED, periodicity=periodicity, installments=installments)
    )

    assert schedule.total_interest == D("30000")
    assert_balances_chain(schedule, D("100000"))


def test_prorated_one_daily_installment_ignores_the_multiple():
    schedule = build_schedule(make_input(method=PRORATED, installments=1))

    assert rows(schedule) == [(D("333"), D("100000"), D("100333"))]


@pytest.mark.parametrize(
    ("periodicity", "expected"),
    [
        ("daily", "6667"),
        ("weekly", "46667"),
        ("biweekly", "100000"),
        ("monthly", "200000"),
    ],
)
def test_prorated_uses_30_day_months(periodicity, expected):
    schedule = build_schedule(make_input(method=PRORATED, periodicity=periodicity))

    assert schedule.total_interest == D(expected)


# Plano por cuota


def test_per_installment_matches_flat_per_credit():
    per_installment = build_schedule(make_input(method=PER_INSTALLMENT, rate=D("0.5")))

    assert per_installment == build_schedule(make_input(method=FLAT))


@pytest.mark.parametrize("periodicity", ["daily", "weekly", "biweekly", "monthly"])
def test_per_installment_ignores_the_periodicity(periodicity):
    schedule = build_schedule(
        make_input(method=PER_INSTALLMENT, rate=D("0.5"), periodicity=periodicity)
    )

    assert schedule.total_interest == D("10000")
    assert rows(schedule) == [(D("500"), D("5000"), D("5500"))] * 20


@pytest.mark.parametrize("periodicity", ["daily", "weekly", "biweekly", "monthly"])
def test_flat_per_credit_ignores_the_periodicity(periodicity):
    schedule = build_schedule(make_input(method=FLAT, periodicity=periodicity))

    assert schedule.total_interest == D("10000")


@pytest.mark.parametrize("method", [FLAT, PRORATED, PER_INSTALLMENT])
def test_zero_rate_has_no_interest_in_any_method(method):
    schedule = build_schedule(make_input(method=method, rate=D("0"), installments=3))

    assert schedule.total_interest == D("0")
    assert [row.payment for row in schedule.installments] == [
        D("33350"),
        D("33350"),
        D("33300"),
    ]
