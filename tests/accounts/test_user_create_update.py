"""Pruebas de la creación y edición de usuarios en pantalla (SPEC 04, paso 7)."""

import re

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import Role, get_role

pytestmark = pytest.mark.django_db

USER_CREATE = reverse("accounts:user_create")
USER_LIST = reverse("accounts:user_list")
LOGIN = reverse("accounts:login")
PASSWORD_CHANGE = reverse("accounts:password_change")

VALID_POST = {
    "username": "ana",
    "first_name": "Ana",
    "last_name": "Pérez",
    "role": Role.COLLECTOR.value,
    "email": "ana@example.com",
    "phone": "3001234567",
    "document_type": "CC",
    "document_number": "1020304050",
}


def update_url(user) -> str:
    return reverse("accounts:user_update", args=[user.pk])


def detail_url(user) -> str:
    return reverse("accounts:user_detail", args=[user.pk])


def shown_password(response) -> str:
    match = re.search(r'id="temporary-password">([^<]+)<', response.content.decode())
    assert match, "La respuesta no muestra la contraseña temporal."
    return match.group(1)


@pytest.fixture
def administrator(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR)


@pytest.fixture
def admin_client(client, administrator):
    client.force_login(administrator)
    return client


# --- Acceso ----------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_get_403_on_create_and_update(client, make_user, role):
    target = make_user("pedro", role=Role.COLLECTOR)
    client.force_login(make_user("otro", role=role))

    assert client.get(USER_CREATE).status_code == 403
    assert client.post(USER_CREATE, VALID_POST).status_code == 403
    assert client.get(update_url(target)).status_code == 403
    assert client.post(update_url(target), VALID_POST).status_code == 403
    assert not User.objects.filter(username="ana").exists()


def test_list_shows_new_user_button_only_with_permission(admin_client):
    content = admin_client.get(USER_LIST).content.decode()

    assert f'href="{USER_CREATE}"' in content


# --- Crear -----------------------------------------------------------------


def test_create_form_has_the_fields_in_order(admin_client):
    response = admin_client.get(USER_CREATE)

    assert list(response.context["form"].fields) == [
        "username",
        "first_name",
        "last_name",
        "role",
        "email",
        "phone",
        "document_type",
        "document_number",
    ]


def test_create_shows_temporary_password_once_without_cache(admin_client):
    response = admin_client.post(USER_CREATE, VALID_POST)

    assert response.status_code == 200
    assert "accounts/users/temporary_password.html" in [
        t.name for t in response.templates
    ]
    assert "no-store" in response["Cache-Control"]
    password = shown_password(response)
    user = User.objects.get(username="ana")
    assert user.check_password(password)
    assert get_role(user) is Role.COLLECTOR
    assert user.must_change_password is True
    assert "Creaste el usuario ana." in response.content.decode()

    detail = admin_client.get(detail_url(user)).content.decode()
    assert password not in detail


def test_password_is_not_kept_in_the_session(admin_client):
    response = admin_client.post(USER_CREATE, VALID_POST)
    password = shown_password(response)

    session_data = str(dict(admin_client.session.items()))
    assert password not in session_data


def test_created_user_logs_in_and_must_change_password(admin_client):
    password = shown_password(admin_client.post(USER_CREATE, VALID_POST))
    admin_client.logout()

    response = admin_client.post(
        LOGIN, {"username": "ana", "password": password}, follow=True
    )

    assert response.redirect_chain[-1][0] == PASSWORD_CHANGE
    assert response.context["user"].username == "ana"


@pytest.mark.parametrize("missing", ["first_name", "last_name", "username", "role"])
def test_create_requires_names_username_and_role(admin_client, missing):
    response = admin_client.post(USER_CREATE, {**VALID_POST, missing: ""})

    assert response.status_code == 200
    assert missing in response.context["form"].errors
    assert not User.objects.filter(username="ana").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phone", "300-123-4567"),
        ("phone", "6011234567"),
        ("username", "ana@example.com"),
        ("role", "Gerente"),
    ],
)
def test_create_rejects_invalid_fields(admin_client, field, value):
    response = admin_client.post(USER_CREATE, {**VALID_POST, field: value})

    assert field in response.context["form"].errors
    assert not User.objects.filter(email="ana@example.com").exists()


def test_create_rejects_incomplete_document(admin_client):
    response = admin_client.post(USER_CREATE, {**VALID_POST, "document_type": ""})

    assert response.context["form"].errors
    assert "Escribe el tipo y el número de documento" in response.content.decode()
    assert not User.objects.filter(username="ana").exists()


def test_create_rejects_duplicate_email(admin_client, make_user):
    make_user("otra", email="ANA@example.com")

    response = admin_client.post(USER_CREATE, VALID_POST)

    assert "Ya existe un usuario con este correo." in response.content.decode()
    assert not User.objects.filter(username="ana").exists()


def test_create_without_optional_fields(admin_client):
    data = {
        **VALID_POST,
        "email": "",
        "phone": "",
        "document_type": "",
        "document_number": "",
    }

    response = admin_client.post(USER_CREATE, data)

    assert response.status_code == 200
    assert shown_password(response)


# --- Editar ----------------------------------------------------------------


def test_update_form_has_no_username(admin_client, make_user):
    target = make_user("pedro", role=Role.COLLECTOR)

    response = admin_client.get(update_url(target))

    assert "username" not in response.context["form"].fields
    assert response.context["form"].initial["role"] == Role.COLLECTOR.value


def test_update_changes_data_and_role(admin_client, make_user):
    target = make_user("pedro", role=Role.COLLECTOR)

    response = admin_client.post(
        update_url(target),
        {
            **VALID_POST,
            "username": "cambiado",
            "first_name": "Pedro",
            "role": Role.SUPERVISOR.value,
        },
    )

    assert response.status_code == 302
    assert response.url == detail_url(target)
    target.refresh_from_db()
    assert target.username == "pedro"
    assert target.first_name == "Pedro"
    assert get_role(target) is Role.SUPERVISOR


def test_editing_self_disables_role_and_ignores_posted_role(
    admin_client, administrator, make_user
):
    make_user("admin2", role=Role.ADMINISTRATOR)

    form = admin_client.get(update_url(administrator)).context["form"]
    assert form.fields["role"].disabled is True

    response = admin_client.post(
        update_url(administrator),
        {**VALID_POST, "first_name": "Ada", "role": Role.VIEWER.value},
    )

    assert response.status_code == 302
    administrator.refresh_from_db()
    assert administrator.first_name == "Ada"
    assert get_role(administrator) is Role.ADMINISTRATOR


def test_update_of_superuser_redirects_with_error(admin_client, make_user):
    root = make_user("root", is_superuser=True, first_name="Root")

    response = admin_client.post(update_url(root), VALID_POST, follow=True)

    assert response.redirect_chain[-1][0] == detail_url(root)
    assert "Los superusuarios no se gestionan desde la aplicación." in (
        response.content.decode()
    )
    root.refresh_from_db()
    assert root.first_name == "Root"


def test_update_last_administrator_role_shows_rule_error(client, make_user):
    root = make_user("root", is_superuser=True)
    administrator = make_user("admin1", role=Role.ADMINISTRATOR)
    client.force_login(root)

    response = client.post(
        update_url(administrator),
        {**VALID_POST, "role": Role.SUPERVISOR.value},
    )

    assert response.status_code == 200
    assert "Debe quedar al menos un administrador activo." in response.content.decode()
    assert get_role(administrator) is Role.ADMINISTRATOR


def test_update_missing_user_is_404(admin_client):
    assert (
        admin_client.get(reverse("accounts:user_update", args=[99999])).status_code
        == 404
    )


def test_detail_shows_edit_button_except_for_superusers(admin_client, make_user):
    target = make_user("pedro", role=Role.COLLECTOR)
    root = make_user("root", is_superuser=True)

    assert (
        f'href="{update_url(target)}"'
        in admin_client.get(detail_url(target)).content.decode()
    )
    assert (
        f'href="{update_url(root)}"'
        not in admin_client.get(detail_url(root)).content.decode()
    )
