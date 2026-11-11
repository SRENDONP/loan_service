"""Context processors de la app core.

`branding` es el único punto del que las plantillas leen la identidad del
negocio. La spec de parámetros globales solo cambia esta función para leer el
nombre y el logo desde `parametros` (ADR-001); las plantillas no se tocan.
"""

from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

# Valores provisionales hasta la spec de parámetros globales.
BUSINESS_NAME = _("Gestión de préstamos")
BRAND_ICON = "fas fa-hand-holding-usd"


def branding(request: HttpRequest) -> dict[str, object]:
    """Entrega el nombre del negocio y el icono de la marca a las plantillas."""
    return {
        "business_name": BUSINESS_NAME,
        "brand_icon": BRAND_ICON,
    }
