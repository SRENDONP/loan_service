"""Excepciones del motor de amortización (SPEC 09, §3.5).

El mensaje va en español sin `gettext`, para los registros y las pruebas. La
interfaz traduce el `code` a su propio texto (SPEC 12).
"""


class AmortizationError(ValueError):
    """Base de los errores del motor, con un código estable y el campo que falla."""

    def __init__(self, message: str, *, code: str, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


class AmortizationInputError(AmortizationError):
    """La entrada rompe una regla de la §3.3."""


class RoundingError(AmortizationError):
    """El redondeo no tiene solución (§3.7)."""


class UnsupportedMethodError(AmortizationError):
    """El método existe en el contrato, pero no tiene estrategia registrada."""
