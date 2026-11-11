"""Pruebas de las utilidades de permisos (SPEC 04, §3.4 y paso 3)."""

import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.urls import include, path
from django.views import View

from apps.accounts.permissions import (
    PermissionRequiredMixin,
    permission_required,
    require_perms,
)
from apps.accounts.roles import Role


class ProtectedView(PermissionRequiredMixin, View):
    permission_required = "accounts.view_user"

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("ok")


@permission_required("accounts.view_user", "accounts.add_user")
def protected_function(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


# Las rutas reales (base.html y 403.html las necesitan) más dos de prueba.
urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("admin/", admin.site.urls),
    path("protegida/clase/", ProtectedView.as_view()),
    path("protegida/funcion/", protected_function),
]

pytestmark = [
    pytest.mark.urls("tests.accounts.test_permissions"),
    pytest.mark.django_db,
]


def test_require_perms_passes_with_all_permissions(make_user):
    administrator = make_user("admin1", role=Role.ADMINISTRATOR)

    require_perms(administrator, "accounts.view_user", "accounts.add_user")


def test_require_perms_raises_if_one_is_missing(make_user):
    administrator = make_user("admin1", role=Role.ADMINISTRATOR)

    with pytest.raises(PermissionDenied):
        require_perms(administrator, "accounts.view_user", "auth.view_group")


def test_require_perms_raises_for_user_without_role(make_user):
    with pytest.raises(PermissionDenied):
        require_perms(make_user(), "accounts.view_user")


def test_require_perms_raises_for_inactive_administrator(make_user):
    administrator = make_user("admin1", role=Role.ADMINISTRATOR, is_active=False)

    with pytest.raises(PermissionDenied):
        require_perms(administrator, "accounts.view_user")


def test_require_perms_passes_for_superuser(make_user):
    require_perms(make_user("root", is_superuser=True), "accounts.view_user")


def test_require_perms_without_permissions_is_a_programming_error(make_user):
    with pytest.raises(ValueError):
        require_perms(make_user())


def test_permission_required_without_permissions_is_a_programming_error():
    with pytest.raises(ValueError):
        permission_required()


@pytest.mark.parametrize("url", ["/protegida/clase/", "/protegida/funcion/"])
def test_user_without_permission_gets_403_without_redirect(client, make_user, url):
    client.force_login(make_user(role=Role.VIEWER))

    response = client.get(url)

    assert response.status_code == 403
    assert "403.html" in [t.name for t in response.templates]


@pytest.mark.parametrize("url", ["/protegida/clase/", "/protegida/funcion/"])
def test_administrator_passes(client, make_user, url):
    client.force_login(make_user("admin1", role=Role.ADMINISTRATOR))

    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.parametrize("url", ["/protegida/clase/", "/protegida/funcion/"])
def test_anonymous_still_goes_to_login(client, url):
    response = client.get(url)

    assert response.status_code == 302
    assert response.url.startswith("/ingresar/")
