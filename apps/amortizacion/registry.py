"""Registro de los métodos de interés del motor (SPEC 09, §3.8).

Cada método es una estrategia que arma la tabla completa. Un método nuevo se
registra con `@register(InterestMethod.X)` sin tocar los existentes.

Lógica pura: no importa Django ni otras apps del proyecto.
"""

from collections.abc import Callable
from typing import Protocol

from .errors import UnsupportedMethodError
from .types import InterestMethod, Schedule, ScheduleInput


class ScheduleStrategy(Protocol):
    def build(self, data: ScheduleInput) -> Schedule: ...


type StrategyClass = type[ScheduleStrategy]


class StrategyRegistry:
    """Las estrategias registradas, una por método.

    El motor usa una sola instancia (`_default`). Las pruebas crean la suya para
    no tocar el registro global.
    """

    def __init__(self) -> None:
        self._strategies: dict[InterestMethod, ScheduleStrategy] = {}

    def register(
        self, method: InterestMethod
    ) -> Callable[[StrategyClass], StrategyClass]:
        def decorator(strategy_class: StrategyClass) -> StrategyClass:
            if method in self._strategies:
                raise ValueError(f"El método {method.value} ya está registrado.")
            self._strategies[method] = strategy_class()
            return strategy_class

        return decorator

    def get(self, method: InterestMethod) -> ScheduleStrategy:
        try:
            return self._strategies[method]
        except KeyError:
            raise UnsupportedMethodError(
                f"El método {method.value} todavía no está disponible.",
                code="unsupported_method",
                field="method",
            ) from None

    def methods(self) -> frozenset[InterestMethod]:
        return frozenset(self._strategies)


_default = StrategyRegistry()


def register(method: InterestMethod) -> Callable[[StrategyClass], StrategyClass]:
    """Decorador de clase que registra la estrategia de `method`."""
    return _default.register(method)


def get_strategy(method: InterestMethod) -> ScheduleStrategy:
    """La estrategia de `method`, o `UnsupportedMethodError` si no está registrada."""
    return _default.get(method)


def registered_methods() -> frozenset[InterestMethod]:
    """Los métodos que tienen estrategia registrada."""
    return _default.methods()
