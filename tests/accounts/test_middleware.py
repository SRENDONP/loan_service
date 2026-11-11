"""Pruebas de ForcePasswordChangeMiddleware (SPEC 03, paso 7)."""

import pytest
from django.conf import settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD_CHANGE = reverse("accounts:password_change")
LOGOUT = reverse("accounts:logout")
LOGIN = reverse("accounts:login")


@pytest.fixture
def flagged_client(client, make_user):
    """Cliente con la sesión de un usuario que debe cambiar la contraseña."""
    client.force_login(make_user("nuevo", must_change_password=True))
    return client


def test_middleware_runs_after_login_required():
    middleware = settings.MIDDLEWARE
    login_required = middleware.index(
        "django.contrib.auth.middleware.LoginRequiredMiddleware"
    )

    assert (
        middleware[login_required + 1]
        == "apps.accounts.middleware.ForcePasswordChangeMiddleware"
    )


@pytest.mark.parametrize("url", ["/", "/componentes/", "/admin/", "/no-existe/"])
def test_flagged_user_is_redirected_to_password_change(flagged_client, settings, url):
    settings.DEBUG = True

    response = flagged_client.get(url)

    assert response.status_code == 302
    assert response.url == PASSWORD_CHANGE


def test_flagged_user_post_is_redirected_too(flagged_client):
    response = flagged_client.post("/")

    assert response.url == PASSWORD_CHANGE


def test_flagged_user_can_open_password_change(flagged_client):
    assert flagged_client.get(PASSWORD_CHANGE).status_code == 200


def test_flagged_user_can_log_out(flagged_client):
    response = flagged_client.post(LOGOUT)

    assert response.url == LOGIN
    assert "_auth_user_id" not in flagged_client.session


def test_flagged_user_can_reach_health(flagged_client):
    assert flagged_client.get(reverse("core:health")).status_code == 200


def test_flagged_user_is_not_redirected_from_static(flagged_client):
    # El cliente de pruebas no sirve estáticos (404), pero no debe redirigir.
    response = flagged_client.get(f"/{settings.STATIC_URL.lstrip('/')}css/app.css")

    assert response.status_code == 404


def test_user_without_flag_is_not_redirected(auth_client):
    assert auth_client.get("/").status_code == 200


def test_anonymous_is_sent_to_login_not_to_password_change(client):
    response = client.get("/")

    assert response.url.startswith(LOGIN)
