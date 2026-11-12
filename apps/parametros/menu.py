"""Menú de parámetros, descubierto por autodiscover_modules("menu") (SPEC 06, §3.8)."""

from django.utils.translation import gettext_lazy as _

from apps.core.navigation import MenuItem, MenuSection, register, register_section

# Antes de "Administración" (orden 900). La SPEC 07 agrega aquí los catálogos.
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
