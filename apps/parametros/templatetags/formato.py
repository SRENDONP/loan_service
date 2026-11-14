"""
Filtros de formato de dinero y fechas (SPEC 06, §3.6).

Se cargan con `{% load formato %}`:

    {{ cuota.valor|moneda }}       -> $1.234.568
    {{ credito.fecha|fecha }}      -> 31/12/2026
    {{ pago.creado|fecha_hora }}   -> 31/12/2026 14:05
    {{ tope.valor|porcentaje }}    -> 25,02

Solo dan formato. Ningún cálculo financiero se hace en las plantillas.
"""

from django import template

from apps.parametros.formatting import (
    format_date,
    format_datetime,
    format_money,
    format_percent,
)

register = template.Library()

register.filter("moneda", format_money)
register.filter("fecha", format_date)
register.filter("fecha_hora", format_datetime)
register.filter("porcentaje", format_percent)
