"""Menú de la app core, descubierto por autodiscover_modules("menu") (SPEC 02)."""

from django.utils.translation import gettext_lazy as _

from apps.core.navigation import MenuItem, MenuSection, register, register_section

register_section(MenuSection(key="principal", label="", order=0))
register_section(MenuSection(key="desarrollo", label=_("Desarrollo"), order=1000))

register(
    MenuItem(
        key="core.home",
        label=_("Inicio"),
        icon="fas fa-fw fa-home",
        section="principal",
        order=0,
        url_name="core:home",
    )
)

register(
    MenuItem(
        key="core.components",
        label=_("Componentes"),
        icon="fas fa-fw fa-puzzle-piece",
        section="desarrollo",
        order=0,
        url_name="core:components",
        debug_only=True,
    )
)
