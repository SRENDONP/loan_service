"""Vistas transversales del sistema."""

import logging

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


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
