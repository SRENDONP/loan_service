"""Vistas transversales del sistema."""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.contrib.messages.storage.base import Message
from django.db import DatabaseError, connection
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods

from .forms import ComponentsDemoForm

logger = logging.getLogger(__name__)

# Datos ficticios y fijos para el catálogo de componentes. Los valores llegan
# ya formateados: la tabla solo los muestra, ordena, busca y pagina.
DEMO_TABLE_ROWS: list[list[str]] = [
    ["Ana Gómez", "1.020.304.050", "Aranjuez", "$ 25.000", "Al día"],
    ["Luis Pérez", "71.234.567", "Belén", "$ 40.000", "En mora"],
    ["Marta Ríos", "43.876.210", "Robledo", "$ 15.000", "Al día"],
    ["Carlos Ruiz", "98.765.432", "Manrique", "$ 30.000", "Al día"],
    ["Diana Mejía", "1.017.223.344", "Castilla", "$ 20.000", "Pagado"],
    ["Jorge Cano", "8.345.120", "Envigado", "$ 50.000", "En mora"],
    ["Paula Arias", "1.036.998.112", "Bello", "$ 18.000", "Al día"],
    ["Andrés Toro", "70.112.334", "Itagüí", "$ 35.000", "Al día"],
    ["Sofía Vélez", "1.152.443.876", "Laureles", "$ 22.000", "Pagado"],
    ["Felipe Mora", "15.678.901", "Buenos Aires", "$ 45.000", "En mora"],
    ["Natalia Gil", "1.040.556.778", "La América", "$ 28.000", "Al día"],
    ["Hernán Ochoa", "3.456.789", "Guayabal", "$ 60.000", "Al día"],
    ["Lucía Zapata", "32.109.876", "Popular", "$ 12.000", "Pagado"],
    ["Mateo Restrepo", "1.001.234.567", "Sabaneta", "$ 33.000", "Al día"],
    ["Valentina Cruz", "1.128.765.432", "Villa Hermosa", "$ 27.000", "En mora"],
]


@require_GET
def home(request: HttpRequest) -> HttpResponse:
    """Página "Inicio". El dashboard la reemplaza en su propia spec."""
    return render(request, "core/home.html")


@login_not_required
@require_GET
def health(request: HttpRequest) -> JsonResponse:
    """
    Indica si la aplicación está viva y llega a la base de datos.

    Es público a propósito (lo usan el healthcheck de Docker y el CI), así que
    no expone versiones, hosts ni mensajes de error: el detalle va al log.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Health check: la base de datos no responde.")
        return JsonResponse({"status": "error", "database": "error"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok"})


CONFIRM_DEMO_ACTION = "confirm-demo"


@require_http_methods(["GET", "POST"])
def components(request: HttpRequest) -> HttpResponse:
    """Catálogo de componentes de la interfaz. Solo existe con DEBUG."""
    if not settings.DEBUG:
        raise Http404

    form = ComponentsDemoForm()
    if request.method == "POST":
        if request.POST.get("action") == CONFIRM_DEMO_ACTION:
            messages.info(request, _("Acción de prueba confirmada."))
            return redirect("core:components")
        form = ComponentsDemoForm(request.POST)
        if form.is_valid():
            messages.success(request, _("El formulario de prueba se envió."))
            return redirect("core:components")

    context = {
        "form": form,
        "confirm_action": CONFIRM_DEMO_ACTION,
        "demo_messages": [
            Message(messages.SUCCESS, _("Ejemplo de mensaje de éxito.")),
            Message(messages.INFO, _("Ejemplo de mensaje informativo.")),
            Message(messages.WARNING, _("Ejemplo de mensaje de advertencia.")),
            Message(messages.ERROR, _("Ejemplo de mensaje de error.")),
        ],
        "table_columns": [
            _("Cliente"),
            _("Documento"),
            _("Barrio"),
            _("Cuota"),
            _("Estado"),
        ],
        "table_rows": DEMO_TABLE_ROWS,
    }
    return render(request, "core/components.html", context)
