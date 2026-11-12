"""
Formato de dinero y fechas para mostrar (SPEC 06, §3.6).

La moneda, sus decimales y el formato de fecha salen de los parámetros
globales. Los separadores de miles y de decimales y el formato de la hora salen
del locale `es-co`, que no es editable.

El redondeo de `format_money` es solo para mostrar: no reemplaza la regla de
redondeo de los cálculos. Nunca se convierte a `float`.
"""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import dateformat, formats, numberformat, timezone

from apps.parametros.services import get_settings

LOCALE = "es-co"


def format_money(value: Decimal | int | None) -> str:
    """El valor con el símbolo de la moneda, por ejemplo `$1.234.568`."""
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise TypeError(
            f"format_money recibe Decimal o int, no {type(value).__name__}."
        )

    settings = get_settings()
    decimals = settings.currency_decimals
    amount = Decimal(value).quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    number = numberformat.format(
        abs(amount),
        decimal_sep=formats.get_format("DECIMAL_SEPARATOR", lang=LOCALE),
        decimal_pos=decimals,
        grouping=formats.get_format("NUMBER_GROUPING", lang=LOCALE),
        thousand_sep=formats.get_format("THOUSAND_SEPARATOR", lang=LOCALE),
        force_grouping=True,
    )
    sign = "-" if amount < 0 else ""
    return f"{sign}{settings.currency_symbol}{number}"


def format_date(value: date | None) -> str:
    """La fecha según el formato de los parámetros, por ejemplo `31/12/2026`."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = _local(value).date()
    return dateformat.format(value, _lowercase_month(get_settings().date_format, value))


def format_datetime(value: datetime | None) -> str:
    """La fecha según los parámetros y la hora local, por ejemplo `31/12/2026 14:05`."""
    if value is None:
        return ""
    local = _local(value)
    time_format = formats.get_format("TIME_FORMAT", lang=LOCALE)
    return f"{format_date(local.date())} {dateformat.format(local, time_format)}"


def _lowercase_month(date_format: str, value: date) -> str:
    """
    Cambia cada `F` sin escapar por el nombre del mes en minúsculas, escapado.

    La traducción de Django escribe los meses con mayúscula ("Diciembre"); en
    español van en minúscula ("31 de diciembre de 2026", SPEC 06, §3.1).
    """
    month = "".join(f"\\{char}" for char in dateformat.format(value, "F").lower())
    result: list[str] = []
    escaped = False
    for char in date_format:
        if escaped:
            result.append(f"\\{char}")
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "F":
            result.append(month)
        else:
            result.append(char)
    return "".join(result)


def _local(value: datetime) -> datetime:
    return timezone.localtime(value) if timezone.is_aware(value) else value
