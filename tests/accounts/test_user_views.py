"""Pruebas de las pantallas de gestión de usuarios (SPEC 04, §3.6 y §3.7)."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.services import deactivate_user

pytestmark = pytest.mark.django_db

USER_LIST = reverse("accounts:user_list")


def detail_url(user) -> str:
    return reverse("accounts:user_detail", args=[user.pk])


@pytest.fixture
def administrator(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR, first_name="Ada")


@pytest.fixture
def admin_client(client, administrator):
    client.force_login(administrator)
    return client


# --- Acceso por rol --------------------------------------------------------


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_get_403(client, make_user, role):
    other = make_user("otro", role=role)
    client.force_login(make_user("sin_permiso", role=role))

    assert client.get(USER_LIST).status_code == 403
    assert client.get(detail_url(other)).status_code == 403


def test_user_without_role_gets_403(auth_client):
    assert auth_client.get(USER_LIST).status_code == 403


def test_anonymous_goes_to_login(client):
    response = client.get(USER_LIST)

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


def test_administrator_sees_the_list(admin_client):
    response = admin_client.get(USER_LIST)

    assert response.status_code == 200
    assert "accounts/users/list.html" in [t.name for t in response.templates]


# --- Listado ---------------------------------------------------------------


def test_list_shows_role_and_status_of_each_user(admin_client, make_user):
    make_user("cobrador1", role=Role.COLLECTOR, first_name="Carlos", last_name="Ruiz")
    make_user(
        "bloqueado",
        role=Role.VIEWER,
        locked_until=timezone.now() + timedelta(minutes=5),
    )
    make_user("inactivo", role=Role.SUPERVISOR, is_active=False)
    make_user("sin_rol")

    content = admin_client.get(USER_LIST).content.decode()

    assert "Carlos Ruiz" in content
    assert '<span class="badge badge-primary">Cajero/Cobrador</span>' in content
    assert '<span class="badge badge-primary">Supervisor</span>' in content
    assert '<span class="badge badge-light">Sin rol</span>' in content
    assert '<span class="badge badge-success">Activo</span>' in content
    assert '<span class="badge badge-warning">Bloqueado</span>' in content
    assert '<span class="badge badge-secondary">Inactivo</span>' in content
    assert "Nunca" in content


def test_list_shows_superuser_badge_without_actions(admin_client, make_user):
    root = make_user("root", is_superuser=True)
    collector = make_user("cobrador1", role=Role.COLLECTOR)

    response = admin_client.get(USER_LIST)

    rows = {row[0]: row for row in response.context["table_rows"]}
    root_row = next(row for key, row in rows.items() if ">root<" in key)
    collector_row = next(row for key, row in rows.items() if ">cobrador1<" in key)
    assert '<span class="badge badge-dark">Superusuario</span>' in root_row[2]
    assert root_row[5] == ""
    assert detail_url(collector) in collector_row[5]
    assert detail_url(root) in root_row[0]


def test_list_escapes_user_data(admin_client, make_user):
    make_user("malicioso", first_name="<script>alert(1)</script>")

    content = admin_client.get(USER_LIST).content.decode()

    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content


def test_list_queries_do_not_grow_with_users(
    admin_client, make_user, django_assert_max_num_queries
):
    for index in range(5):
        make_user(f"cobrador{index}", role=Role.COLLECTOR)
    admin_client.get(USER_LIST)

    with django_assert_max_num_queries(12):
        admin_client.get(USER_LIST)


# --- Ficha -----------------------------------------------------------------


def test_detail_shows_data_and_access(admin_client, make_user):
    target = make_user(
        "pedro",
        role=Role.COLLECTOR,
        first_name="Pedro",
        last_name="Gómez",
        phone="3001234567",
        document_type="CC",
        document_number="1020304050",
        must_change_password=True,
    )

    response = admin_client.get(detail_url(target))

    content = response.content.decode()
    assert response.status_code == 200
    assert "Pedro Gómez" in content
    assert "3001234567" in content
    assert "CC 1020304050" in content
    assert '<span class="badge badge-primary">Cajero/Cobrador</span>' in content
    assert "Pendiente en su próximo ingreso" in content
    assert "Desactivación" not in content


def test_detail_shows_lock_end_when_locked(admin_client, make_user):
    target = make_user("pedro", locked_until=timezone.now() + timedelta(minutes=5))

    content = admin_client.get(detail_url(target)).content.decode()

    assert "Bloqueado hasta" in content


def test_detail_of_inactive_user_shows_deactivation(
    admin_client, administrator, make_user
):
    target = make_user("pedro", role=Role.COLLECTOR)
    deactivate_user(administrator, target, reason="Terminó su contrato")

    content = admin_client.get(detail_url(target)).content.decode()

    assert "Desactivación" in content
    assert "Terminó su contrato" in content
    assert "admin1" in content


def test_detail_of_superuser_warns_that_it_is_not_managed_here(admin_client, make_user):
    root = make_user("root", is_superuser=True)

    content = admin_client.get(detail_url(root)).content.decode()

    assert "superusuario" in content
    assert '<span class="badge badge-dark">Superusuario</span>' in content


def test_detail_of_missing_user_is_404(admin_client):
    assert (
        admin_client.get(reverse("accounts:user_detail", args=[99999])).status_code
        == 404
    )


# --- Menú ------------------------------------------------------------------


def test_administrator_sees_users_in_menu(admin_client):
    content = admin_client.get(reverse("core:home")).content.decode()

    assert "Administración" in content
    assert f'href="{USER_LIST}"' in content


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_do_not_see_users_in_menu(client, make_user, role):
    client.force_login(make_user("otro", role=role))

    content = client.get(reverse("core:home")).content.decode()

    assert "Administración" not in content
    assert f'href="{USER_LIST}"' not in content


def test_users_menu_entry_is_active_on_the_list(admin_client):
    content = admin_client.get(USER_LIST).content.decode()

    assert f'href="{USER_LIST}" aria-current="page"' in content
