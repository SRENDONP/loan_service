"""
Menú de parámetros, descubierto por autodiscover_modules("menu").

Parámetros globales (SPEC 06, §3.8) y el submenú de catálogos (SPEC 07, §3.9).
"""

from django.utils.translation import gettext_lazy as _

from apps.core.navigation import MenuItem, MenuSection, register, register_section
from apps.parametros.catalogs import CATALOGS

# Antes de "Administración" (orden 900).
register_section(MenuSection(key="configuracion", label=_("Configuración"), order=800))

register(
    MenuItem(
        key="parametros.global",
        label=_("Parámetros globales"),
        icon="fas fa-fw fa-sliders-h",
        section="configuracion",
        order=10,
        url_name="parametros:global",
        permissions=("parametros.view_globalsettings",),
    )
)

# Un hijo por catálogo de texto, en el orden de CATALOGS, y los festivos al
# final. El menú oculta el padre si el usuario no ve ningún hijo.
register(
    MenuItem(
        key="parametros.catalogos",
        label=_("Catálogos"),
        icon="fas fa-fw fa-list",
        section="configuracion",
        order=20,
        children=(
            *(
                MenuItem(
                    key=f"parametros.catalogos.{catalog.slug}",
                    label=catalog.label,
                    icon="",
                    section="configuracion",
                    order=catalog.order,
                    url_name=catalog.list_url_name,
                    permissions=(catalog.permission("view"),),
                )
                for catalog in CATALOGS
            ),
            MenuItem(
                key="parametros.catalogos.festivos",
                label=_("Festivos"),
                icon="",
                section="configuracion",
                order=70,
                url_name="parametros:holiday_list",
                permissions=("parametros.view_holiday",),
            ),
        ),
    )
)
