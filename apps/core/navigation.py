"""Registro de módulos del menú lateral (SPEC 02, §3.1).

Cada app declara sus secciones y entradas en su propio `menu.py`, y
`CoreConfig.ready()` los descubre con `autodiscover_modules("menu")`, el mismo
mecanismo del admin de Django. Agregar un módulo al menú no toca `apps.core`.

Ejemplo de `apps/<app>/menu.py`::

    from django.utils.translation import gettext_lazy as _

    from apps.core.navigation import MenuItem, MenuSection, register, register_section

    register_section(MenuSection(key="operacion", label=_("Operación"), order=10))
    register(
        MenuItem(
            key="clientes.list",
            label=_("Clientes"),
            icon="fas fa-fw fa-users",
            section="operacion",
            order=10,
            url_name="clientes:list",
            permissions=("clientes.view_cliente",),
        )
    )

El registro guarda `url_name` como texto y solo hace `reverse` en
`build_menu`, al pintar el menú: al importar los `menu.py` las URLs todavía no
están cargadas.
"""

from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.urls import reverse


@dataclass(frozen=True)
class MenuSection:
    key: str  # "principal", "desarrollo", ...
    label: str  # gettext_lazy; "" = sin encabezado
    order: int


@dataclass(frozen=True)
class MenuItem:
    key: str  # único en todo el registro
    label: str  # gettext_lazy
    icon: str  # clases de Font Awesome, p. ej. "fas fa-fw fa-home"
    section: str  # MenuSection.key
    order: int
    url_name: str | None = None  # p. ej. "core:home"; None si tiene children
    permissions: tuple[str, ...] = ()  # () = visible para todos
    children: tuple[MenuItem, ...] = ()  # un solo nivel
    debug_only: bool = False


@dataclass(frozen=True)
class RenderedItem:
    """Una entrada visible para el usuario actual, lista para la plantilla."""

    key: str
    label: str
    icon: str
    url: str | None
    active: bool
    children: tuple[RenderedItem, ...] = ()

    @property
    def collapse_id(self) -> str:
        """`id` del submenú colapsable, como `collapseTwo` en SB Admin 2."""
        return "collapse-" + self.key.replace(".", "-").replace("_", "-")


@dataclass(frozen=True)
class RenderedSection:
    """Una sección con al menos una entrada visible."""

    key: str
    label: str
    items: tuple[RenderedItem, ...]


def _sort_key(item: MenuItem) -> tuple[int, str]:
    return (item.order, item.key)


class MenuRegistry:
    """Secciones y entradas del menú. `registry` es la instancia global."""

    def __init__(self) -> None:
        self._sections: dict[str, MenuSection] = {}
        self._items: dict[str, MenuItem] = {}
        self._keys: set[str] = set()  # claves de entradas y de sus hijos

    # Registro -----------------------------------------------------------

    def register_section(self, section: MenuSection) -> None:
        if section.key in self._sections:
            raise ImproperlyConfigured(
                f"La sección de menú '{section.key}' ya está registrada."
            )
        self._sections[section.key] = section

    def register(self, item: MenuItem) -> None:
        if item.section not in self._sections:
            raise ImproperlyConfigured(
                f"La entrada de menú '{item.key}' usa la sección "
                f"'{item.section}', que no está registrada."
            )
        keys = [item.key]
        self._validate_target(item)
        for child in item.children:
            if child.children:
                raise ImproperlyConfigured(
                    f"La entrada de menú '{child.key}' es un hijo de "
                    f"'{item.key}' y no puede tener hijos: el menú solo "
                    "admite un nivel de submenú."
                )
            self._validate_target(child)
            keys.append(child.key)

        for key in keys:
            if key in self._keys or keys.count(key) > 1:
                raise ImproperlyConfigured(
                    f"La clave de menú '{key}' ya está registrada."
                )

        self._items[item.key] = item
        self._keys.update(keys)

    @staticmethod
    def _validate_target(item: MenuItem) -> None:
        if not item.url_name and not item.children:
            raise ImproperlyConfigured(
                f"La entrada de menú '{item.key}' necesita un url_name o children."
            )

    # Consulta -----------------------------------------------------------

    def all_items(self) -> list[MenuItem]:
        """Todas las entradas registradas, incluidos los hijos."""
        result: list[MenuItem] = []
        for item in self._items.values():
            result.append(item)
            result.extend(item.children)
        return result

    def build_menu(self, request: HttpRequest) -> list[RenderedSection]:
        """Devuelve solo las secciones y entradas visibles para `request.user`."""
        user = getattr(request, "user", None) or AnonymousUser()
        match = getattr(request, "resolver_match", None)
        current = match.view_name if match else None

        def is_visible(item: MenuItem) -> bool:
            if item.debug_only and not settings.DEBUG:
                return False
            return user.has_perms(item.permissions)

        def render(item: MenuItem) -> RenderedItem | None:
            if not is_visible(item):
                return None
            if item.children:
                children = tuple(
                    rendered
                    for child in sorted(item.children, key=_sort_key)
                    if (rendered := render(child)) is not None
                )
                if not children:
                    return None
                return RenderedItem(
                    key=item.key,
                    label=item.label,
                    icon=item.icon,
                    url=None,
                    active=any(child.active for child in children),
                    children=children,
                )
            return RenderedItem(
                key=item.key,
                label=item.label,
                icon=item.icon,
                url=reverse(item.url_name),
                active=item.url_name == current,
            )

        sections: list[RenderedSection] = []
        for section in sorted(self._sections.values(), key=lambda s: (s.order, s.key)):
            items = tuple(
                rendered
                for item in sorted(self._items.values(), key=_sort_key)
                if item.section == section.key
                if (rendered := render(item)) is not None
            )
            if items:
                sections.append(
                    RenderedSection(key=section.key, label=section.label, items=items)
                )
        return sections


registry = MenuRegistry()


def register_section(section: MenuSection) -> None:
    registry.register_section(section)


def register(item: MenuItem) -> None:
    registry.register(item)


def build_menu(request: HttpRequest) -> list[RenderedSection]:
    return registry.build_menu(request)
