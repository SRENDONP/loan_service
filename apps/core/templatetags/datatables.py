"""Etiqueta `{% datatables_i18n %}`: textos de DataTables en español (SPEC 02).

Los textos los entrega el servidor con gettext por `json_script`, con el id
`datatables-i18n`, y `static/js/app.js` los pasa a DataTables. El JavaScript
no tiene textos fijos. Se usa una vez por página, en el bloque `extra_js`.
"""

from django import template
from django.utils.formats import get_format
from django.utils.html import json_script
from django.utils.safestring import SafeString
from django.utils.translation import gettext as _

register = template.Library()

ELEMENT_ID = "datatables-i18n"


def datatables_language() -> dict[str, object]:
    """Opción `language` de DataTables 1.10 en el idioma activo."""
    return {
        # Separadores del idioma activo (es-co: "," y "."), para ordenar cifras.
        "decimal": get_format("DECIMAL_SEPARATOR"),
        "thousands": get_format("THOUSAND_SEPARATOR"),
        "emptyTable": _("No hay registros para mostrar."),
        "info": _("Mostrando _START_ a _END_ de _TOTAL_ registros"),
        "infoEmpty": _("Mostrando 0 a 0 de 0 registros"),
        "infoFiltered": _("(filtrados de _MAX_ registros en total)"),
        "lengthMenu": _("Mostrar _MENU_ registros"),
        "loadingRecords": _("Cargando…"),
        "processing": _("Procesando…"),
        "search": _("Buscar:"),
        "zeroRecords": _("No hay registros que coincidan con la búsqueda."),
        "paginate": {
            "first": _("Primera"),
            "last": _("Última"),
            "next": _("Siguiente"),
            "previous": _("Anterior"),
        },
        "aria": {
            "sortAscending": _(": activar para ordenar de forma ascendente"),
            "sortDescending": _(": activar para ordenar de forma descendente"),
        },
    }


@register.simple_tag
def datatables_i18n() -> SafeString:
    return json_script(datatables_language(), ELEMENT_ID)
