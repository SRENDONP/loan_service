"""Pruebas de las vistas de acciones sobre usuarios (SPEC 04, §3.6 y paso 8)."""

import re
from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import Role

pytestmark = pytest.mark.django_db

POST_ACTIONS = [
    "accounts:user_reactivate",
    "accounts:user_unlock",
    "accounts:user_reset_password",
    "accounts:user_logout_sessions",
]


def url(name: str, user: User) -> str:
    return reverse(name, args=[user.pk])


def detail_url(user: User) -> str:
    return url("accounts:user_detail", user)


def messages_of(response) -> list[str]:
    return [str(message) for message in response.context["messages"]]


@pytest.fixture
def administrator(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR)


@pytest.fixture
def admin_client(client, administrator):
    client.force_login(administrator)
    return client


@pytest.fixture
def target(make_user):
    return make_user("pedro", role=Role.COLLECTOR)


# --- Acceso y métodos ------------------------------------------------------


@pytest.mark.parametrize("name", POST_ACTIONS)
def test_post_only_actions_reject_get_with_405(admin_client, target, name):
    assert admin_client.get(url(name, target)).status_code == 405


@pytest.mark.parametrize("name", [*POST_ACTIONS, "accounts:user_deactivate"])
@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_get_403(client, make_user, target, name, role):
    client.force_login(make_user("otro", role=role))

    assert client.post(url(name, target), {"reason": "x"}).status_code == 403
    target.refresh_from_db()
    assert target.is_active is True


@pytest.mark.parametrize("name", [*POST_ACTIONS, "accounts:user_deactivate"])
def test_actions_on_missing_user_are_404(admin_client, name):
    missing = User(pk=99999)

    assert admin_client.post(url(name, missing), {"reason": "x"}).status_code == 404


@pytest.mark.parametrize("name", [*POST_ACTIONS, "accounts:user_deactivate"])
def test_actions_on_superuser_redirect_with_error(admin_client, make_user, name):
    root = make_user("root", is_superuser=True)

    response = admin_client.post(url(name, root), {"reason": "x"}, follow=True)

    assert response.redirect_chain[-1][0] == detail_url(root)
    assert "Los superusuarios no se gestionan desde la aplicación." in messages_of(
        response
    )
    root.refresh_from_db()
    assert root.is_active is True


# --- Desactivar ------------------------------------------------------------


def test_deactivate_page_shows_reason_form(admin_client, target):
    response = admin_client.get(url("accounts:user_deactivate", target))

    assert response.status_code == 200
    assert "accounts/users/deactivate.html" in [t.name for t in response.templates]
    assert "reason" in response.context["form"].fields
    assert "sus sesiones abiertas se cerrarán" in response.content.decode()


def test_deactivate_with_reason(admin_client, administrator, target):
    other = Client()
    other.force_login(target)

    response = admin_client.post(
        url("accounts:user_deactivate", target),
        {"reason": "Terminó su contrato"},
        follow=True,
    )

    assert response.redirect_chain[-1][0] == detail_url(target)
    assert "Desactivaste a pedro y se cerraron sus sesiones." in messages_of(response)
    target.refresh_from_db()
    assert target.is_active is False
    assert target.deactivation_reason == "Terminó su contrato"
    assert target.deactivated_by == administrator
    assert other.get(reverse("core:home")).status_code == 302


@pytest.mark.parametrize("reason", ["", "    ", "x" * 501])
def test_deactivate_with_invalid_reason_shows_form_error(admin_client, target, reason):
    response = admin_client.post(
        url("accounts:user_deactivate", target), {"reason": reason}
    )

    assert response.status_code == 200
    assert "reason" in response.context["form"].errors
    target.refresh_from_db()
    assert target.is_active is True


def test_deactivate_self_redirects_with_error(admin_client, administrator, make_user):
    make_user("admin2", role=Role.ADMINISTRATOR)

    response = admin_client.post(
        url("accounts:user_deactivate", administrator),
        {"reason": "Prueba"},
        follow=True,
    )

    assert "No puedes desactivar tu propia cuenta." in messages_of(response)
    administrator.refresh_from_db()
    assert administrator.is_active is True


def test_deactivate_last_administrator_redirects_with_error(client, make_user):
    root = make_user("root", is_superuser=True)
    administrator = make_user("admin1", role=Role.ADMINISTRATOR)
    client.force_login(root)

    response = client.post(
        url("accounts:user_deactivate", administrator),
        {"reason": "Prueba"},
        follow=True,
    )

    assert response.redirect_chain[-1][0] == detail_url(administrator)
    assert "Debe quedar al menos un administrador activo." in messages_of(response)
    administrator.refresh_from_db()
    assert administrator.is_active is True


# --- Reactivar -------------------------------------------------------------


def test_reactivate(admin_client, make_user):
    inactive = make_user(
        "inactivo",
        role=Role.VIEWER,
        is_active=False,
        deactivation_reason="Vacaciones",
    )

    response = admin_client.post(url("accounts:user_reactivate", inactive), follow=True)

    assert response.redirect_chain[-1][0] == detail_url(inactive)
    assert any("Reactivaste a inactivo." in m for m in messages_of(response))
    inactive.refresh_from_db()
    assert inactive.is_active is True
    assert inactive.deactivation_reason == ""
    assert inactive.must_change_password is True


def test_reactivate_active_user_shows_error_and_changes_nothing(admin_client, target):
    response = admin_client.post(url("accounts:user_reactivate", target), follow=True)

    assert "El usuario ya está activo." in messages_of(response)
    target.refresh_from_db()
    assert target.must_change_password is False


# --- Desbloquear -----------------------------------------------------------


def test_unlock_locked_user(admin_client, target):
    target.locked_until = timezone.now() + timedelta(minutes=10)
    target.save()

    response = admin_client.post(url("accounts:user_unlock", target), follow=True)

    assert "Desbloqueaste a pedro." in messages_of(response)
    target.refresh_from_db()
    assert target.locked_until is None


def test_unlock_user_that_is_not_locked_shows_info(admin_client, target):
    response = admin_client.post(url("accounts:user_unlock", target), follow=True)

    assert "La cuenta no estaba bloqueada." in messages_of(response)


def test_unlock_inactive_user_shows_error(admin_client, make_user):
    inactive = make_user("inactivo", role=Role.VIEWER, is_active=False)

    response = admin_client.post(url("accounts:user_unlock", inactive), follow=True)

    assert any("está inactivo" in m for m in messages_of(response))


# --- Restablecer contraseña ------------------------------------------------


def test_reset_password_shows_new_password_once_without_cache(admin_client, target):
    response = admin_client.post(url("accounts:user_reset_password", target))

    assert response.status_code == 200
    assert "no-store" in response["Cache-Control"]
    match = re.search(r'id="temporary-password">([^<]+)<', response.content.decode())
    assert match
    target.refresh_from_db()
    assert target.check_password(match.group(1))
    assert target.must_change_password is True
    assert "Contraseña restablecida" in response.content.decode()


def test_reset_own_password_redirects_with_error(admin_client, administrator):
    response = admin_client.post(
        url("accounts:user_reset_password", administrator), follow=True
    )

    assert response.redirect_chain[-1][0] == detail_url(administrator)
    assert any("Cambiar contraseña" in m for m in messages_of(response))


# --- Cerrar sesiones -------------------------------------------------------


def test_logout_sessions_reports_count(admin_client, target):
    for _ in range(2):
        Client().force_login(target)

    response = admin_client.post(
        url("accounts:user_logout_sessions", target), follow=True
    )

    assert "Cerraste 2 sesiones de pedro." in messages_of(response)


def test_logout_sessions_singular_message(admin_client, target):
    Client().force_login(target)

    response = admin_client.post(
        url("accounts:user_logout_sessions", target), follow=True
    )

    assert "Cerraste 1 sesión de pedro." in messages_of(response)


# --- Botones de la ficha ---------------------------------------------------


def test_detail_of_active_user_shows_actions_with_confirmation(admin_client, target):
    target.locked_until = timezone.now() + timedelta(minutes=10)
    target.save()

    content = admin_client.get(detail_url(target)).content.decode()

    for name in [
        "accounts:user_reset_password",
        "accounts:user_unlock",
        "accounts:user_logout_sessions",
    ]:
        assert re.search(
            rf'<form method="post" action="{re.escape(url(name, target))}"[^>]*\s+'
            r'data-confirm="',
            content,
        ), name
    assert f'href="{url("accounts:user_deactivate", target)}"' in content
    assert url("accounts:user_reactivate", target) not in content


def test_detail_hides_unlock_when_not_locked(admin_client, target):
    content = admin_client.get(detail_url(target)).content.decode()

    assert url("accounts:user_unlock", target) not in content


def test_detail_of_inactive_user_only_offers_reactivate(admin_client, make_user):
    inactive = make_user("inactivo", role=Role.VIEWER, is_active=False)

    content = admin_client.get(detail_url(inactive)).content.decode()

    assert url("accounts:user_reactivate", inactive) in content
    for name in [
        "accounts:user_reset_password",
        "accounts:user_logout_sessions",
        "accounts:user_deactivate",
    ]:
        assert url(name, inactive) not in content


def test_detail_of_self_and_superuser_has_no_actions(
    admin_client, administrator, make_user
):
    root = make_user("root", is_superuser=True)

    for user in (administrator, root):
        content = admin_client.get(detail_url(user)).content.decode()
        assert url("accounts:user_reset_password", user) not in content
        assert url("accounts:user_deactivate", user) not in content

    own = admin_client.get(detail_url(administrator)).content.decode()
    assert "Esta es tu cuenta." in own


def test_detail_shows_only_actions_the_actor_may_use(client, make_user, target):
    from django.contrib.auth.models import Permission

    actor = make_user("solo_desbloquea")
    actor.user_permissions.add(
        *Permission.objects.filter(codename__in=["view_user", "unlock_user"])
    )
    target.locked_until = timezone.now() + timedelta(minutes=10)
    target.save()
    client.force_login(actor)

    content = client.get(detail_url(target)).content.decode()

    assert url("accounts:user_unlock", target) in content
    assert url("accounts:user_reset_password", target) not in content
    assert url("accounts:user_deactivate", target) not in content


def test_action_base_view_requires_perform():
    from apps.accounts.views import UserActionView

    with pytest.raises(NotImplementedError):
        UserActionView().perform()


def test_create_view_shows_service_rule_errors(admin_client, monkeypatch):
    from apps.accounts import views
    from apps.accounts.services import UserRuleError

    def reject(*args, **kwargs):
        raise UserRuleError("Regla de prueba.")

    monkeypatch.setattr(views, "create_user", reject)
    data = {
        "username": "ana",
        "first_name": "Ana",
        "last_name": "Pérez",
        "role": Role.VIEWER.value,
    }

    response = admin_client.post(reverse("accounts:user_create"), data)

    assert response.status_code == 200
    assert "Regla de prueba." in response.content.decode()
    assert not User.objects.filter(username="ana").exists()


def test_logout_sessions_without_sessions_shows_info(admin_client, target):
    response = admin_client.post(
        url("accounts:user_logout_sessions", target), follow=True
    )

    assert "pedro no tenía sesiones abiertas." in messages_of(response)


def test_form_labels_match_the_detail_page(admin_client):
    form = admin_client.get(reverse("accounts:user_create")).context["form"]

    assert form.fields["first_name"].label == "Nombres"
    assert form.fields["last_name"].label == "Apellidos"
