"""Etiqueta `{% sidebar_menu %}`: pinta el menú lateral (SPEC 02, §2).

El menú se calcula aquí, y no en un context processor, para que solo se
construya en las páginas que lo pintan. Así `500.html` no depende de él.
"""

from typing import Any

from django import template

from apps.core import navigation

register = template.Library()


@register.inclusion_tag("core/menu.html", takes_context=True)
def sidebar_menu(context: template.Context) -> dict[str, Any]:
    request = context.get("request")
    sections = navigation.build_menu(request) if request is not None else []
    return {"sections": sections}
