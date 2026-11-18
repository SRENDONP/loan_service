"""Registro de métodos del motor (SPEC 09, §3.8)."""

from decimal import Decimal

import pytest

from apps.amortizacion.errors import UnsupportedMethodError
from apps.amortizacion.registry import (
    StrategyRegistry,
    get_strategy,
    registered_methods,
)
from apps.amortizacion.types import InterestMethod, Schedule, ScheduleInput


class FakeStrategy:
    def build(self, data: ScheduleInput) -> Schedule:
        return Schedule(
            installments=(),
            regular_payment=Decimal("0"),
            total_principal=data.principal,
            total_interest=Decimal("0"),
            total_payment=data.principal,
        )


def test_register_returns_the_class_and_stores_an_instance():
    registry = StrategyRegistry()

    decorated = registry.register(InterestMethod.FRENCH)(FakeStrategy)

    assert decorated is FakeStrategy
    assert isinstance(registry.get(InterestMethod.FRENCH), FakeStrategy)
    assert registry.methods() == frozenset({InterestMethod.FRENCH})


def test_registering_a_method_twice_raises():
    registry = StrategyRegistry()
    registry.register(InterestMethod.GERMAN)(FakeStrategy)

    with pytest.raises(ValueError, match="german"):
        registry.register(InterestMethod.GERMAN)(FakeStrategy)


def test_unregistered_method_raises_unsupported():
    with pytest.raises(UnsupportedMethodError) as excinfo:
        StrategyRegistry().get(InterestMethod.DECLINING_BALANCE)

    assert excinfo.value.code == "unsupported_method"
    assert excinfo.value.field == "method"


def test_new_registry_is_empty():
    assert StrategyRegistry().methods() == frozenset()


def test_module_functions_use_the_default_registry():
    for method in InterestMethod:
        if method in registered_methods():
            assert get_strategy(method) is get_strategy(method)
        else:
            with pytest.raises(UnsupportedMethodError):
                get_strategy(method)
