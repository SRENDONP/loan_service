"""Pruebas del registro de módulos del menú (SPEC 02, §3.1)."""

import re
import sys

import pytest
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, modify_settings
from django.urls import include, path, resolve, reverse
from django.utils.module_loading import autodiscover_modules

from apps.core import navigation
from apps.core.navigation import MenuItem, MenuRegistry, MenuSection

# URLconf propia de este módulo: las pruebas no dependen de las rutas reales.


def _view(request: HttpRequest) -> HttpResponse:
    return HttpResponse()


_nav_patterns = (
    [
        path("alpha/", _view, name="alpha"),
        path("beta/", _view, name="beta"),
        path("gamma/", _view, name="gamma"),
    ],
    "nav-test",
)
urlpatterns = [path("nav/", include(_nav_patterns))]

pytestmark = pytest.mark.urls("tests.core.test_navigation")

PERMISSION = "auth.view_group"


# Fixtures y ayudas ------------------------------------------------------


@pytest.fixture
def registry() -> MenuRegistry:
    """Registro aislado con una sección principal sin encabezado."""
    reg = MenuRegistry()
    reg.register_section(MenuSection(key="principal", label="", order=0))
    return reg


@pytest.fixture
def user_with_perm(django_user_model):
    user = django_user_model.objects.create_user("con_permiso", password="x")
    app_label, codename = PERMISSION.split(".")
    user.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    # Recarga para no arrastrar la caché de permisos.
    return django_user_model.objects.get(pk=user.pk)


@pytest.fixture
def user_without_perm(django_user_model):
    return django_user_model.objects.create_user("sin_permiso", password="x")


def make_request(path: str = "/nav/alpha/", user=None) -> HttpRequest:
    request = RequestFactory().get(path)
    request.resolver_match = resolve(path)
    request.user = user if user is not None else AnonymousUser()
    return request


def item(key: str, **kwargs) -> MenuItem:
    defaults = {
        "label": key,
        "icon": "fas fa-fw fa-circle",
        "section": "principal",
        "order": 0,
        "url_name": "nav-test:alpha",
    }
    defaults.update(kwargs)
    return MenuItem(key=key, **defaults)


def keys(sections) -> list[list[str]]:
    return [[i.key for i in s.items] for s in sections]


# Orden ------------------------------------------------------------------


def test_sections_are_sorted_by_order(registry):
    registry.register_section(MenuSection(key="z_ultima", label="Z", order=100))
    registry.register_section(MenuSection(key="a_media", label="A", order=10))
    registry.register(item("x.ultima", section="z_ultima"))
    registry.register(item("x.media", section="a_media"))
    registry.register(item("x.principal"))

    sections = registry.build_menu(make_request())

    assert [s.key for s in sections] == ["principal", "a_media", "z_ultima"]


def test_items_are_sorted_by_order_then_key(registry):
    registry.register(item("c", order=2))
    registry.register(item("b", order=1))
    registry.register(item("a", order=2))

    assert keys(registry.build_menu(make_request())) == [["b", "a", "c"]]


def test_children_are_sorted_and_urls_reversed(registry):
    registry.register(
        item(
            "padre",
            url_name=None,
            children=(
                item("hijo.b", order=2, url_name="nav-test:beta"),
                item("hijo.a", order=1, url_name="nav-test:gamma"),
            ),
        )
    )

    (parent,) = registry.build_menu(make_request())[0].items

    assert parent.url is None
    assert [c.key for c in parent.children] == ["hijo.a", "hijo.b"]
    assert [c.url for c in parent.children] == ["/nav/gamma/", "/nav/beta/"]
    assert parent.collapse_id == "collapse-padre"


# Permisos ---------------------------------------------------------------


@pytest.mark.django_db
def test_item_with_permission_visible_only_to_user_with_it(
    registry, user_with_perm, user_without_perm
):
    registry.register(item("publica"))
    registry.register(item("privada", permissions=(PERMISSION,)))

    def visible_for(user) -> list[list[str]]:
        return keys(registry.build_menu(make_request(user=user)))

    assert visible_for(user_with_perm) == [["privada", "publica"]]
    assert visible_for(user_without_perm) == [["publica"]]
    assert visible_for(AnonymousUser()) == [["publica"]]


def test_request_without_user_is_treated_as_anonymous(registry):
    registry.register(item("publica"))
    registry.register(item("privada", permissions=(PERMISSION,)))
    request = RequestFactory().get("/nav/alpha/")

    assert keys(registry.build_menu(request)) == [["publica"]]


# Padres y secciones vacías ----------------------------------------------


def test_parent_hidden_when_no_child_is_visible(registry):
    registry.register(
        item(
            "padre",
            url_name=None,
            children=(item("hijo", permissions=(PERMISSION,)),),
        )
    )
    registry.register(item("otra"))

    assert keys(registry.build_menu(make_request())) == [["otra"]]


def test_parent_shows_only_visible_children(registry):
    registry.register(
        item(
            "padre",
            url_name=None,
            children=(
                item("hijo.visible"),
                item("hijo.oculto", permissions=(PERMISSION,)),
            ),
        )
    )

    (parent,) = registry.build_menu(make_request())[0].items

    assert [c.key for c in parent.children] == ["hijo.visible"]


def test_section_without_visible_items_is_not_shown(registry):
    registry.register_section(MenuSection(key="vacia", label="Vacía", order=1))
    registry.register_section(MenuSection(key="oculta", label="Oculta", order=2))
    registry.register(item("x"))
    registry.register(item("y", section="oculta", permissions=(PERMISSION,)))

    sections = registry.build_menu(make_request())

    assert [s.key for s in sections] == ["principal"]


# DEBUG ------------------------------------------------------------------


def test_debug_only_items_appear_only_with_debug(registry, settings):
    registry.register(item("normal"))
    registry.register(item("solo_debug", debug_only=True))

    settings.DEBUG = True
    assert keys(registry.build_menu(make_request())) == [["normal", "solo_debug"]]

    settings.DEBUG = False
    assert keys(registry.build_menu(make_request())) == [["normal"]]


# Entrada activa ---------------------------------------------------------


def test_item_matching_current_view_is_active(registry):
    registry.register(item("alpha", url_name="nav-test:alpha"))
    registry.register(item("beta", url_name="nav-test:beta"))

    items = registry.build_menu(make_request("/nav/beta/"))[0].items

    assert {i.key: i.active for i in items} == {"alpha": False, "beta": True}


def test_parent_is_active_when_a_child_is_active(registry):
    registry.register(
        item(
            "padre",
            url_name=None,
            children=(
                item("hijo.alpha", url_name="nav-test:alpha"),
                item("hijo.gamma", url_name="nav-test:gamma"),
            ),
        )
    )
    registry.register(item("otra", url_name="nav-test:beta"))

    items = registry.build_menu(make_request("/nav/gamma/"))[0].items
    by_key = {i.key: i for i in items}
    parent = by_key["padre"]

    assert parent.active is True
    assert [c.active for c in parent.children] == [False, True]
    assert by_key["otra"].active is False


def test_nothing_active_without_resolver_match(registry):
    registry.register(item("alpha"))
    request = RequestFactory().get("/no-existe/")

    (rendered,) = registry.build_menu(request)[0].items

    assert rendered.active is False


# Validaciones -----------------------------------------------------------


def test_duplicate_section_key_raises(registry):
    with pytest.raises(ImproperlyConfigured, match="principal"):
        registry.register_section(MenuSection(key="principal", label="", order=1))


def test_duplicate_item_key_raises(registry):
    registry.register(item("repetida"))

    with pytest.raises(ImproperlyConfigured, match="repetida"):
        registry.register(item("repetida"))


def test_child_key_colliding_with_existing_key_raises(registry):
    registry.register(item("existente"))

    with pytest.raises(ImproperlyConfigured, match="existente"):
        registry.register(item("padre", url_name=None, children=(item("existente"),)))
    # El registro fallido no deja rastro.
    registry.register(item("padre"))


def test_duplicate_key_inside_same_item_raises(registry):
    with pytest.raises(ImproperlyConfigured, match="padre"):
        registry.register(item("padre", url_name=None, children=(item("padre"),)))


def test_unknown_section_raises(registry):
    with pytest.raises(ImproperlyConfigured, match="no_existe"):
        registry.register(item("x", section="no_existe"))


def test_child_with_children_raises(registry):
    nieto = item("nieto")
    hijo = item("hijo", url_name=None, children=(nieto,))

    with pytest.raises(ImproperlyConfigured, match="un nivel"):
        registry.register(item("padre", url_name=None, children=(hijo,)))


def test_item_without_url_name_or_children_raises(registry):
    with pytest.raises(ImproperlyConfigured, match="url_name o children"):
        registry.register(item("vacia", url_name=None))


def test_child_without_url_name_raises(registry):
    with pytest.raises(ImproperlyConfigured, match="hijo"):
        registry.register(
            item("padre", url_name=None, children=(item("hijo", url_name=None),))
        )


# Registro global y descubrimiento ---------------------------------------


@pytest.fixture
def global_registry(monkeypatch) -> MenuRegistry:
    """Sustituye el registro global por uno vacío durante la prueba."""
    fresh = MenuRegistry()
    monkeypatch.setattr(navigation, "registry", fresh)
    return fresh


def test_module_functions_use_global_registry(global_registry):
    navigation.register_section(MenuSection(key="s", label="S", order=0))
    navigation.register(item("x", section="s"))

    assert keys(navigation.build_menu(make_request())) == [["x"]]


def test_app_menu_py_is_discovered_without_editing_core(global_registry):
    """Una app nueva aparece en el menú con solo agregar su menu.py."""
    sys.modules.pop("tests.core.menu_app.menu", None)
    try:
        with modify_settings(INSTALLED_APPS={"append": "tests.core.menu_app"}):
            autodiscover_modules("menu")
    finally:
        sys.modules.pop("tests.core.menu_app.menu", None)

    sections = navigation.build_menu(make_request())

    assert [(s.key, s.label) for s in sections] == [("prueba", "Prueba")]
    assert [i.key for i in sections[0].items] == ["test_menu_app.page"]
    assert sections[0].items[0].active is True


@pytest.mark.urls("config.urls")
def test_every_registered_url_name_can_be_reversed():
    """Las entradas reales de los menu.py apuntan a rutas que existen."""
    for menu_item in navigation.registry.all_items():
        if menu_item.url_name:
            reverse(menu_item.url_name)


def test_active_child_renders_parent_active_and_submenu_shown(registry):
    """En el HTML del menú, el padre activo tiene `active` y su submenú `show`."""
    registry.register(
        item(
            "padre",
            url_name=None,
            children=(
                item("hijo.alpha", url_name="nav-test:alpha"),
                item("hijo.gamma", url_name="nav-test:gamma"),
            ),
        )
    )
    registry.register(
        item(
            "otro",
            url_name=None,
            children=(item("otro.hijo", url_name="nav-test:beta"),),
        )
    )
    sections = registry.build_menu(make_request("/nav/gamma/"))

    html = render_to_string("core/menu.html", {"sections": sections})

    assert re.search(
        r'<li class="nav-item active">\s*<a class="nav-link" href="#" '
        r'data-toggle="collapse" data-target="#collapse-padre" aria-expanded="true"',
        html,
    )
    assert '<div id="collapse-padre" class="collapse show"' in html
    assert (
        '<a class="collapse-item active" href="/nav/gamma/" aria-current="page">'
        in html
    )
    # El otro padre queda cerrado y sin `active`.
    assert re.search(
        r'<li class="nav-item">\s*<a class="nav-link collapsed" href="#" '
        r'data-toggle="collapse" data-target="#collapse-otro" aria-expanded="false"',
        html,
    )
    assert '<div id="collapse-otro" class="collapse"' in html
