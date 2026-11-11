"""Pruebas de las vistas y del contexto de plantillas de core (SPEC 02)."""

import json
import re

import pytest
from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.template import engines
from django.test import RequestFactory
from django.urls import include, path, reverse

from apps.core.context_processors import branding

HOME = reverse("core:home")


def nav_item_for(html: str, href: str) -> str:
    """Devuelve la etiqueta <li class="nav-item..."> que contiene el enlace."""
    pattern = rf'<li class="(nav-item[^"]*)">\s*<a class="nav-link" href="{href}"'
    match = re.search(pattern, html)
    assert match, f"No hay una entrada del menú para {href}"
    return match.group(1)


# Página "Inicio" --------------------------------------------------------


@pytest.mark.django_db
def test_home_renders_inside_base_layout(client):
    response = client.get(HOME)

    assert response.status_code == 200
    assert "base.html" in [t.name for t in response.templates]
    html = response.content.decode()
    assert 'id="accordionSidebar"' in html
    assert 'class="navbar navbar-expand navbar-light bg-white topbar' in html
    assert 'class="sticky-footer' in html
    assert "Gestión de préstamos" in html
    assert '<html lang="es-co">' in html


@pytest.mark.django_db
def test_home_marks_inicio_as_active(client):
    html = client.get(HOME).content.decode()

    assert nav_item_for(html, HOME) == "nav-item active"
    assert "Inicio" in html


@pytest.mark.django_db
def test_topbar_hides_user_menu_for_anonymous(client):
    html = client.get(HOME).content.decode()

    assert 'id="userDropdown"' not in html
    assert 'id="logoutModal"' not in html


@pytest.mark.django_db
def test_topbar_shows_user_menu_when_authenticated(client, django_user_model):
    user = django_user_model.objects.create_user("cajero1", password="x")
    client.force_login(user)

    html = client.get(HOME).content.decode()

    assert 'id="userDropdown"' in html
    assert 'id="logoutModal"' in html
    assert "cajero1" in html
    assert f'action="{reverse("admin:logout")}"' in html


@pytest.mark.django_db
def test_topbar_has_no_search_alerts_or_messages(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("u", password="x"))

    html = client.get(HOME).content.decode()

    assert "alertsDropdown" not in html
    assert "messagesDropdown" not in html
    assert "navbar-search" not in html


@pytest.mark.django_db
def test_empty_sections_do_not_show_their_heading(client, settings):
    """Sin DEBUG, la sección "Desarrollo" queda vacía y no se pinta."""
    settings.DEBUG = False

    html = client.get(HOME).content.decode()

    assert "sidebar-heading" not in html


# Context processor branding --------------------------------------------


def test_branding_returns_business_name_and_icon(rf: RequestFactory):
    context = branding(rf.get("/"))

    assert str(context["business_name"]) == "Gestión de préstamos"
    assert context["brand_icon"] == "fas fa-hand-holding-usd"


def test_branding_reaches_the_template_context(rf: RequestFactory):
    """El context processor está registrado en TEMPLATES."""
    template = engines["django"].from_string("{{ business_name }}|{{ brand_icon }}")

    html = template.render({}, request=rf.get("/"))

    assert html == "Gestión de préstamos|fas fa-hand-holding-usd"


# Mensajes ---------------------------------------------------------------


def messages_view(request: HttpRequest) -> HttpResponse:
    """Agrega un mensaje de cada nivel y renderiza una página del layout."""
    messages.success(request, "Mensaje de éxito")
    messages.info(request, "Mensaje informativo")
    messages.warning(request, "Mensaje de advertencia")
    messages.error(request, "Mensaje de error")
    return render(request, "core/home.html")


urlpatterns = [
    path("", include("apps.core.urls")),
    path("admin/", admin.site.urls),
    path("mensajes/", messages_view, name="messages-demo"),
]


@pytest.mark.django_db
@pytest.mark.urls("tests.core.test_views")
def test_each_message_level_renders_as_bootstrap_alert(client):
    html = client.get("/mensajes/").content.decode()

    for level, text in [
        ("success", "Mensaje de éxito"),
        ("info", "Mensaje informativo"),
        ("warning", "Mensaje de advertencia"),
        ("danger", "Mensaje de error"),
    ]:
        pattern = (
            rf'<div class="alert alert-{level} alert-dismissible fade show" '
            rf'role="alert">\s*{text}\s*<button type="button" class="close" '
            r'data-dismiss="alert"'
        )
        assert re.search(pattern, html), f"Falta la alerta {level}"
    assert "alert-error" not in html


# Tablas con DataTables --------------------------------------------------


def test_datatables_i18n_delivers_spanish_texts_as_json():
    html = engines["django"].from_string("{% load datatables %}{% datatables_i18n %}")
    rendered = html.render({})

    match = re.fullmatch(
        r'<script id="datatables-i18n" type="application/json">(.*)</script>',
        rendered,
    )
    assert match
    language = json.loads(match.group(1))
    assert language["search"] == "Buscar:"
    assert language["paginate"]["next"] == "Siguiente"
    assert language["info"] == "Mostrando _START_ a _END_ de _TOTAL_ registros"
    assert (language["decimal"], language["thousands"]) == (",", ".")


def test_datatable_include_renders_table_structure():
    template = engines["django"].from_string(
        '{% include "includes/datatable.html" with table_id="demo" title=title '
        "columns=columns rows=rows %}"
    )

    html = template.render(
        {
            "title": "Clientes",
            "columns": ["Nombre", "Saldo"],
            "rows": [["Ana", "$ 1.000"], ["<b>Luis</b>", "$ 2.500"]],
        }
    )

    assert re.search(
        r'<table class="table table-bordered" id="demo"[^>]*\bdata-datatable\b'
        r'[^>]*aria-labelledby="demo-title"',
        html,
    )
    assert '<h6 class="m-0 font-weight-bold text-primary" id="demo-title">' in html
    assert html.count("<th>Nombre</th>") == 2  # thead y tfoot
    assert "<td>$ 1.000</td>" in html
    assert "<td>&lt;b&gt;Luis&lt;/b&gt;</td>" in html  # los valores se escapan


# Modal de confirmación --------------------------------------------------


@pytest.mark.django_db
def test_base_layout_includes_single_confirm_modal(client):
    html = client.get(HOME).content.decode()

    assert html.count('id="confirmModal"') == 1
    assert 'data-default-label="Confirmar"' in html
    assert 'id="confirmModalCancel">Cancelar</button>' in html


# Página de componentes --------------------------------------------------

COMPONENTS = reverse("core:components")
VALID_FORM = {
    "name": "Ana Gómez",
    "email": "ana@example.com",
    "request_type": "consulta",
    "notes": "",
    "accepts_terms": "on",
}


@pytest.mark.django_db
def test_components_page_available_with_debug(client, settings):
    settings.DEBUG = True

    response = client.get(COMPONENTS)

    assert response.status_code == 200
    html = response.content.decode()
    for level in ("success", "info", "warning", "danger"):
        assert f"alert alert-{level} alert-dismissible" in html
    assert html.count("<tr>") == 15 + 2  # filas + thead + tfoot
    assert 'id="datatables-i18n"' in html
    assert "vendor/datatables/jquery.dataTables.min.js" in html
    assert "vendor/datatables/dataTables.bootstrap4.min.css" in html
    assert 'data-confirm="¿Quieres ejecutar la acción de prueba?"' in html
    assert 'name="accepts_terms"' in html
    assert "btn-icon-split" in html


@pytest.mark.django_db
def test_components_page_is_404_without_debug(client, settings):
    settings.DEBUG = False

    assert client.get(COMPONENTS).status_code == 404
    assert client.post(COMPONENTS, VALID_FORM).status_code == 404


@pytest.mark.django_db
def test_components_menu_entry_only_with_debug(client, settings):
    settings.DEBUG = True
    html = client.get(COMPONENTS).content.decode()
    assert re.search(
        r'<div class="sidebar-heading">\s*Desarrollo\s*</div>\s*'
        r"(<!--[^>]*-->\s*)?"
        rf'<li class="nav-item active">\s*<a class="nav-link" href="{COMPONENTS}"',
        html,
    )
    assert nav_item_for(html, HOME) == "nav-item"

    settings.DEBUG = False
    html = client.get(HOME).content.decode()
    assert COMPONENTS not in html
    assert "Desarrollo" not in html


@pytest.mark.django_db
def test_components_invalid_post_shows_errors(client, settings):
    settings.DEBUG = True

    response = client.post(COMPONENTS, {**VALID_FORM, "email": "no-es-correo"})

    assert response.status_code == 200
    html = response.content.decode()
    assert "form-control is-invalid" in html
    assert 'class="invalid-feedback" id="id_email_error"' in html
    assert response.context["form"].errors["email"]


@pytest.mark.django_db
def test_components_valid_post_redirects_with_success_message(client, settings):
    settings.DEBUG = True

    response = client.post(COMPONENTS, VALID_FORM, follow=True)

    assert response.redirect_chain == [(COMPONENTS, 302)]
    assert "El formulario de prueba se envió." in response.content.decode()


@pytest.mark.django_db
def test_components_confirm_action_redirects_with_message(client, settings):
    settings.DEBUG = True

    response = client.post(COMPONENTS, {"action": "confirm-demo"}, follow=True)

    assert response.redirect_chain == [(COMPONENTS, 302)]
    assert "Acción de prueba confirmada." in response.content.decode()
