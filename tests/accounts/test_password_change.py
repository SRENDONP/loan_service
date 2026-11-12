"""Pruebas del cambio de contraseña (SPEC 03, paso 7)."""

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

PASSWORD_CHANGE = reverse("accounts:password_change")
HOME = reverse("core:home")
LOGIN = reverse("accounts:login")
NEW_PASSWORD = "cuota2027"


def change_data(old_password: str, new_password: str = NEW_PASSWORD) -> dict:
    return {
        "old_password": old_password,
        "new_password1": new_password,
        "new_password2": new_password,
    }


def login(client: Client, username: str, password: str) -> None:
    response = client.post(LOGIN, {"username": username, "password": password})
    assert response.status_code == 302


# Pantalla ----------------------------------------------------------------


def test_page_renders_inside_layout(auth_client):
    response = auth_client.get(PASSWORD_CHANGE)

    assert response.status_code == 200
    assert "base.html" in [t.name for t in response.templates]
    html = response.content.decode()
    assert 'id="accordionSidebar"' in html
    assert '<h1 class="h3 mb-4 text-gray-800">Cambiar contraseña</h1>' in html
    assert 'class="card shadow mb-4"' in html
    assert 'name="old_password"' in html
    assert "Tu contraseña debe tener al menos 8 caracteres." in html


def test_mandatory_change_shows_alert(client, make_user):
    client.force_login(make_user(must_change_password=True))

    html = client.get(PASSWORD_CHANGE).content.decode()

    assert 'class="alert alert-warning"' in html


def test_voluntary_change_has_no_alert(auth_client):
    html = auth_client.get(PASSWORD_CHANGE).content.decode()

    assert 'class="alert alert-warning"' not in html


def test_anonymous_is_sent_to_login(client):
    response = client.get(PASSWORD_CHANGE)

    assert response.url.startswith(LOGIN)


# Cambio ------------------------------------------------------------------


def test_mandatory_change_turns_flag_off_and_unlocks_home(client, make_user, password):
    user = make_user(must_change_password=True)
    client.force_login(user)

    response = client.post(PASSWORD_CHANGE, change_data(password), follow=True)

    assert response.redirect_chain == [(HOME, 302)]
    assert "Cambiaste tu contraseña." in response.content.decode()
    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.check_password(NEW_PASSWORD)
    assert client.get(HOME).status_code == 200


def test_voluntary_change_keeps_flag_off(auth_client, user, password):
    auth_client.post(PASSWORD_CHANGE, change_data(password))

    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.check_password(NEW_PASSWORD)


def test_wrong_current_password_shows_errors(client, make_user, password):
    user = make_user(must_change_password=True)
    client.force_login(user)

    response = client.post(PASSWORD_CHANGE, change_data("otra2026"))

    assert response.status_code == 200
    assert "old_password" in response.context["form"].errors
    assert "is-invalid" in response.content.decode()
    user.refresh_from_db()
    assert user.must_change_password is True
    assert user.check_password(password)


@pytest.mark.parametrize("new_password", ["abcdefgh", "12345678", "abc1234"])
def test_new_password_must_follow_policy(auth_client, user, password, new_password):
    response = auth_client.post(PASSWORD_CHANGE, change_data(password, new_password))

    assert response.status_code == 200
    assert "new_password2" in response.context["form"].errors
    user.refresh_from_db()
    assert user.check_password(password)


def test_mismatched_confirmation_shows_errors(auth_client, password):
    data = change_data(password)
    data["new_password2"] = "cuota2028"

    response = auth_client.post(PASSWORD_CHANGE, data)

    assert "new_password2" in response.context["form"].errors


# Sesiones ------------------------------------------------------------------


def test_current_session_stays_and_other_sessions_close(make_user, password):
    user = make_user("ana")
    current, other = Client(), Client()
    login(current, "ana", password)
    login(other, "ana", password)
    assert other.get(HOME).status_code == 200

    current.post(PASSWORD_CHANGE, change_data(password))

    assert current.get(HOME).status_code == 200
    response = other.get(HOME)
    assert response.status_code == 302
    assert response.url.startswith(LOGIN)
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


# Topbar ------------------------------------------------------------------


def test_user_menu_has_password_change_divider_and_logout(auth_client):
    html = auth_client.get(HOME).content.decode()

    menu = html[html.index('aria-labelledby="userDropdown"') :]
    change = menu.index(f'href="{PASSWORD_CHANGE}"')
    divider = menu.index('<div class="dropdown-divider"></div>')
    logout = menu.index('data-target="#logoutModal"')
    assert change < divider < logout
    assert "Cambiar contraseña" in menu
    assert "Cerrar sesión" in menu


def test_change_follows_the_min_length_parameter(
    auth_client, user, password, global_settings
):
    # SPEC 06, §5: con 12 de longitud mínima, una contraseña de 11 se rechaza.
    global_settings.password_min_length = 12
    global_settings.save()

    response = auth_client.post(PASSWORD_CHANGE, change_data(password, "cuota202701"))

    assert response.status_code == 200
    assert "Debe tener al menos 12 caracteres." in response.content.decode()
    user.refresh_from_db()
    assert user.check_password(password)

    accepted = auth_client.post(PASSWORD_CHANGE, change_data(password, "cuota2027012"))

    assert accepted.status_code == 302
