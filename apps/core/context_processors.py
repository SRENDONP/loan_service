"""Context processors de la app core.

`branding` es el único punto del que las plantillas leen la identidad del
negocio. Desde la SPEC 06 toma el nombre y el icono de los parámetros globales,
por medio de su servicio (ADR-001); las plantillas no cambiaron.
"""

from django.http import HttpRequest

from apps.parametros.services import get_settings


def branding(request: HttpRequest) -> dict[str, object]:
    """Entrega el nombre del negocio y el icono de la marca a las plantillas."""
    settings = get_settings()
    return {
        "business_name": settings.business_name,
        "brand_icon": settings.brand_icon,
    }
