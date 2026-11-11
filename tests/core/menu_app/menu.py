"""Menú de la app de prueba, descubierto por autodiscover_modules("menu")."""

from apps.core.navigation import MenuItem, MenuSection, register, register_section

register_section(MenuSection(key="prueba", label="Prueba", order=50))
register(
    MenuItem(
        key="test_menu_app.page",
        label="Página de prueba",
        icon="fas fa-fw fa-flask",
        section="prueba",
        order=1,
        url_name="nav-test:alpha",
    )
)
