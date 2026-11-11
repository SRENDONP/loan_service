"""Menú de la app de cuentas, descubierto por autodiscover_modules("menu") (SPEC 04)."""

from django.utils.translation import gettext_lazy as _

from apps.core.navigation import MenuItem, MenuSection, register, register_section

register_section(
    MenuSection(key="administracion", label=_("Administración"), order=900)
)

register(
    MenuItem(
        key="accounts.users",
        label=_("Usuarios"),
        icon="fas fa-fw fa-users-cog",
        section="administracion",
        order=10,
        url_name="accounts:user_list",
        permissions=("accounts.view_user",),
    )
)
