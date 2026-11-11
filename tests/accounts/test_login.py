"""Pruebas del inicio y el cierre de sesión (SPEC 03, paso 5)."""

from datetime import timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.accounts.forms import LoginForm

pytestmark = pytest.mark.django_db

LOGIN = reverse("accounts:login")
LOGOUT = reverse("accounts:logout")
HOME = reverse("core:home")

INVALID_LOGIN_MESSAGE = str(LoginForm.error_messages["invalid_login"])


def post_login(client, username: str, password: str, **extra):
    return client.post(LOGIN, {"username": username, "password": password, **extra})


def error_messages(response) -> list[str]:
    return list(response.context["form"].non_field_errors())


# Página de login ----------------------------------------------------------


def test_login_page_uses_auth_layout(client):
    response = client.get(LOGIN)

    assert response.status_code == 200
    assert [t.name for t in response.templates][:2] == [
        "accounts/login.html",
        "accounts/auth_base.html",
    ]
    html = response.content.decode()
    assert '<body class="bg-gradient-primary">' in html
    assert 'class="card o-hidden border-0 shadow-lg my-5"' in html
    assert 'class="col-xl-6 col-lg-7 col-md-9"' in html
    assert "Gestión de préstamos" in html
    assert 'id="accordionSidebar"' not in html


def test_login_page_fields_use_auth_style(client):
    html = client.get(LOGIN).content.decode()

    assert 'class="form-control form-control-user"' in html
    assert 'placeholder="Usuario o correo"' in html
    assert 'placeholder="Contraseña"' in html
    assert '<label class="sr-only" for="id_username">Usuario o correo</label>' in html
    assert 'class="btn btn-primary btn-user btn-block"' in html


def test_login_page_has_no_removed_template_parts(client):
    html = client.get(LOGIN).content.decode()

    for removed in (
        "bg-login-image",
        "bg-password-image",
        "Recuérdame",
        "Remember",
        "btn-google",
        "btn-facebook",
        "register",
        "Crear una cuenta",
    ):
        assert removed not in html


def test_authenticated_user_is_redirected_from_login(client, make_user):
    client.force_login(make_user())

    response = client.get(LOGIN)

    assert response.status_code == 302
    assert response.url == HOME


# Inicio de sesión -----------------------------------------------------------


def test_superuser_login_redirects_home(client, password):
    from apps.accounts.models import User

    User.objects.create_superuser("admin", "admin@example.com", password)

    response = post_login(client, "admin", password)

    assert response.status_code == 302
    assert response.url == HOME
    assert client.session["_auth_user_id"]


def test_login_with_email_in_other_case(client, make_user, password):
    user = make_user("ana", email="ana@example.com")

    response = post_login(client, "ANA@Example.com", password)

    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_login_follows_safe_next(client, make_user, password):
    make_user("ana")

    response = post_login(client, "ana", password, next="/componentes/")

    assert response.url == "/componentes/"


def test_login_ignores_unsafe_next(client, make_user, password):
    make_user("ana")

    response = post_login(client, "ana", password, next="https://evil.example.com/")

    assert response.url == HOME


def test_login_resets_failed_attempts(client, make_user, password):
    user = make_user("ana", failed_login_attempts=3)

    post_login(client, "ana", password)

    user.refresh_from_db()
    assert user.failed_login_attempts == 0


# Mismo mensaje para todo fallo -----------------------------------------------


def test_all_login_failures_show_the_same_message(client, make_user, password):
    make_user("ana")
    make_user("inactivo", is_active=False)
    make_user("bloqueado", locked_until=timezone.now() + timedelta(minutes=10))

    responses = [
        post_login(client, "ana", "otra2026"),
        post_login(client, "nadie", password),
        post_login(client, "inactivo", password),
        post_login(client, "bloqueado", password),
    ]

    for response in responses:
        assert response.status_code == 200
        assert error_messages(response) == [INVALID_LOGIN_MESSAGE]
        assert "_auth_user_id" not in client.session


def test_invalid_login_message_warns_about_lockout(client):
    response = post_login(client, "nadie", "otra2026")

    html = response.content.decode()
    assert "la cuenta se bloquea unos minutos" in html
    assert 'class="alert alert-danger"' in html


def test_empty_fields_show_field_errors(client):
    response = post_login(client, "", "")

    form = response.context["form"]
    assert "username" in form.errors
    assert "password" in form.errors
    assert "is-invalid" in response.content.decode()


def test_fifth_failure_through_the_view_locks_the_account(client, make_user, password):
    user = make_user("ana")

    for _ in range(5):
        post_login(client, "ana", "otra2026")
    response = post_login(client, "ana", password)

    user.refresh_from_db()
    assert user.locked_until is not None
    assert error_messages(response) == [INVALID_LOGIN_MESSAGE]
    assert "_auth_user_id" not in client.session


# Cierre de sesión -----------------------------------------------------------


def test_logout_by_get_is_not_allowed(client, make_user):
    client.force_login(make_user())

    response = client.get(LOGOUT)

    assert response.status_code == 405
    assert "_auth_user_id" in client.session


def test_logout_by_post_redirects_to_login_with_message(client, make_user):
    client.force_login(make_user())

    response = client.post(LOGOUT)

    assert response.status_code == 302
    assert response.url == LOGIN
    assert "_auth_user_id" not in client.session
    assert [str(m) for m in get_messages(response.wsgi_request)] == ["Cerraste sesión."]


def test_logout_message_is_shown_on_login_page(client, make_user):
    client.force_login(make_user())

    response = client.post(LOGOUT, follow=True)

    assert "Cerraste sesión." in response.content.decode()


def test_logout_modal_posts_to_accounts_logout(client, make_user):
    client.force_login(make_user())

    html = client.get(HOME).content.decode()

    assert f'<form method="post" action="{LOGOUT}"' in html
