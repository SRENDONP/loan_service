"""Pruebas de las páginas de error 403, 403 CSRF, 404 y 500 (SPEC 02)."""

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.template.loader import get_template
from django.test import RequestFactory
from django.urls import include, path, reverse
from django.views.defaults import server_error

SECRET = "detalle-interno-secreto"


def forbidden_view(request: HttpRequest) -> HttpResponse:
    raise PermissionDenied(SECRET)


# Las rutas reales más una vista de prueba que lanza PermissionDenied.
urlpatterns = [
    path("", include("apps.core.urls")),
    path("admin/", admin.site.urls),
    path("prohibido/", forbidden_view, name="forbidden"),
]

pytestmark = [
    pytest.mark.urls("tests.core.test_error_pages"),
    pytest.mark.django_db,
]


@pytest.fixture(autouse=True)
def no_debug(settings):
    settings.DEBUG = False


def template_names(response) -> list[str]:
    return [t.name for t in response.templates]


def assert_no_leaks(html: str) -> None:
    assert SECRET not in html
    assert "Traceback" not in html
    assert "DEBUG" not in html


def test_404_uses_layout_and_spanish_text(client):
    response = client.get(f"/no-existe-{SECRET}/")

    assert response.status_code == 404
    assert "404.html" in template_names(response)
    assert "base.html" in template_names(response)
    html = response.content.decode()
    assert "Página no encontrada" in html
    assert 'id="accordionSidebar"' in html
    assert_no_leaks(html)


def test_403_on_permission_denied(client):
    response = client.get(reverse("forbidden"))

    assert response.status_code == 403
    assert "403.html" in template_names(response)
    html = response.content.decode()
    assert "Acceso denegado" in html
    assert "No tienes permiso para ver esta página." in html
    assert 'id="accordionSidebar"' in html
    assert_no_leaks(html)


def test_403_csrf_on_post_without_token(csrf_client):
    response = csrf_client.post(reverse("core:home"))

    assert response.status_code == 403
    assert "403_csrf.html" in template_names(response)
    html = response.content.decode()
    assert "No se pudo verificar la solicitud" in html
    assert 'id="accordionSidebar"' in html
    # Ni el motivo técnico de Django ni su texto en inglés.
    assert "CSRF" not in html
    assert "Forbidden" not in html
    assert_no_leaks(html)


def test_500_renders_with_empty_context_and_without_menu():
    html = get_template("500.html").render()

    assert "Error del servidor" in html
    assert '<html lang="es-co">' in html
    assert "sb-admin-2.min.css" in html
    assert 'id="accordionSidebar"' not in html
    assert "Gestión de préstamos" not in html  # no usa context processors
    assert_no_leaks(html)


def test_500_handler_uses_template():
    response = server_error(RequestFactory().get("/"))

    assert response.status_code == 500
    assert "Error del servidor" in response.content.decode()
