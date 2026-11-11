"""Pruebas de los servicios de acciones sobre usuarios (SPEC 04, §3.5 y paso 5)."""

from datetime import timedelta

import pytest
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.accounts.services import (
    UserRuleError,
    deactivate_user,
    logout_user_sessions,
    reactivate_user,
    reset_user_password,
    unlock_user,
)

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
LOGIN = reverse("accounts:login")


@pytest.fixture
def administrator(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR)


@pytest.fixture
def superuser(make_user):
    return make_user("root", is_superuser=True)


@pytest.fixture
def target(make_user):
    return make_user("pedro", role=Role.COLLECTOR)


def open_session(user: User) -> Client:
    client = Client()
    client.force_login(user)
    assert client.get(HOME).status_code == 200
    return client


def sessions_of(user: User) -> int:
    return sum(
        1
        for session in Session.objects.all()
        if session.get_decoded().get("_auth_user_id") == str(user.pk)
    )


# --- Desactivar ------------------------------------------------------------


def test_deactivate_fills_fields_and_closes_sessions(administrator, target):
    client = open_session(target)

    deactivate_user(administrator, target, reason="  Ya no trabaja aquí  ")

    target.refresh_from_db()
    assert target.is_active is False
    assert target.deactivated_at is not None
    assert target.deactivated_by == administrator
    assert target.deactivation_reason == "Ya no trabaja aquí"
    assert sessions_of(target) == 0
    response = client.get(HOME)
    assert response.status_code == 302
    assert response.url.startswith(LOGIN)


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_deactivate_requires_reason(administrator, target, reason):
    with pytest.raises(UserRuleError, match="motivo"):
        deactivate_user(administrator, target, reason=reason)

    target.refresh_from_db()
    assert target.is_active is True


def test_deactivate_rejects_reason_longer_than_500(administrator, target):
    with pytest.raises(UserRuleError, match="500"):
        deactivate_user(administrator, target, reason="x" * 501)

    deactivate_user(administrator, target, reason="x" * 500)
    target.refresh_from_db()
    assert target.is_active is False


def test_deactivate_last_administrator_fails_even_with_superuser(
    administrator, superuser
):
    with pytest.raises(UserRuleError, match="al menos un administrador activo"):
        deactivate_user(superuser, administrator, reason="Prueba")

    administrator.refresh_from_db()
    assert administrator.is_active is True


def test_administrator_can_deactivate_another_administrator(administrator, make_user):
    other = make_user("admin2", role=Role.ADMINISTRATOR)

    deactivate_user(administrator, other, reason="Retiro")

    other.refresh_from_db()
    assert other.is_active is False


def test_deactivate_already_inactive_user_fails(administrator, make_user):
    inactive = make_user("inactivo", role=Role.VIEWER, is_active=False)

    with pytest.raises(UserRuleError, match="inactivo"):
        deactivate_user(administrator, inactive, reason="Otra vez")


def test_deactivate_does_not_close_other_users_sessions(administrator, target):
    open_session(administrator)
    open_session(target)

    deactivate_user(administrator, target, reason="Retiro")

    assert sessions_of(administrator) == 1


# --- Reactivar -------------------------------------------------------------


def test_reactivate_clears_fields_and_forces_password_change(administrator, target):
    deactivate_user(administrator, target, reason="Vacaciones largas")

    reactivate_user(administrator, target)

    target.refresh_from_db()
    assert target.is_active is True
    assert target.deactivated_at is None
    assert target.deactivated_by is None
    assert target.deactivation_reason == ""
    assert target.must_change_password is True


def test_reactivate_active_user_fails(administrator, target):
    with pytest.raises(UserRuleError, match="ya está activo"):
        reactivate_user(administrator, target)


# --- Desbloquear -----------------------------------------------------------


def test_unlock_clears_lock(administrator, target):
    target.failed_login_attempts = 3
    target.locked_until = timezone.now() + timedelta(minutes=10)
    target.save()

    unlock_user(administrator, target)

    target.refresh_from_db()
    assert target.failed_login_attempts == 0
    assert target.locked_until is None
    assert target.status == "active"


def test_unlock_user_that_is_not_locked_changes_nothing(administrator, target):
    unlock_user(administrator, target)

    target.refresh_from_db()
    assert target.locked_until is None


# --- Restablecer contraseña ------------------------------------------------


def test_reset_password_unlocks_forces_change_and_closes_sessions(
    administrator, target, password
):
    target.locked_until = timezone.now() + timedelta(minutes=10)
    target.failed_login_attempts = 2
    target.save()
    open_session(target)
    open_session(target)

    new_password = reset_user_password(administrator, target)

    target.refresh_from_db()
    assert target.check_password(new_password)
    assert not target.check_password(password)
    assert target.must_change_password is True
    assert target.locked_until is None
    assert target.failed_login_attempts == 0
    assert sessions_of(target) == 0


# --- Cerrar sesiones -------------------------------------------------------


def test_logout_sessions_closes_all_and_returns_count(administrator, target):
    first = open_session(target)
    open_session(target)
    open_session(administrator)

    closed = logout_user_sessions(administrator, target)

    assert closed == 2
    assert sessions_of(target) == 0
    assert sessions_of(administrator) == 1
    target.refresh_from_db()
    assert target.is_active is True
    assert first.get(HOME).status_code == 302


def test_logout_sessions_without_sessions_returns_zero(administrator, target):
    assert logout_user_sessions(administrator, target) == 0


def test_logout_sessions_ignores_expired_sessions(administrator, target):
    open_session(target)
    Session.objects.update(expire_date=timezone.now() - timedelta(minutes=1))

    assert logout_user_sessions(administrator, target) == 0


# --- Reglas comunes --------------------------------------------------------

ACTIONS = {
    "deactivate": lambda actor, user: deactivate_user(actor, user, reason="Motivo"),
    "reactivate": reactivate_user,
    "unlock": unlock_user,
    "reset_password": reset_user_password,
    "logout_sessions": logout_user_sessions,
}

PERMISSIONS = {
    "deactivate": "deactivate_user",
    "reactivate": "deactivate_user",
    "unlock": "unlock_user",
    "reset_password": "reset_user_password",
    "logout_sessions": "logout_user_sessions",
}


@pytest.mark.parametrize("action", ACTIONS)
def test_no_action_applies_to_oneself(administrator, make_user, action):
    make_user("admin2", role=Role.ADMINISTRATOR)

    with pytest.raises(UserRuleError) as excinfo:
        ACTIONS[action](administrator, administrator)

    assert excinfo.value.code == "self"
    administrator.refresh_from_db()
    assert administrator.is_active is True


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("actor_name", ["administrator", "superuser"])
def test_no_action_applies_to_a_superuser(request, make_user, action, actor_name):
    actor = request.getfixturevalue(actor_name)
    other_superuser = make_user("root2", is_superuser=True)

    with pytest.raises(UserRuleError) as excinfo:
        ACTIONS[action](actor, other_superuser)

    assert excinfo.value.code == "superuser"


@pytest.mark.parametrize("action", ["unlock", "reset_password", "logout_sessions"])
def test_actions_on_inactive_user_fail(administrator, make_user, action):
    inactive = make_user("inactivo", role=Role.VIEWER, is_active=False)

    with pytest.raises(UserRuleError) as excinfo:
        ACTIONS[action](administrator, inactive)

    assert excinfo.value.code == "inactive"


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_each_action_requires_its_permission(make_user, target, action, role):
    actor = make_user("sin_permiso", role=role)
    if action == "reactivate":
        target.is_active = False
        target.save()

    with pytest.raises(PermissionDenied):
        ACTIONS[action](actor, target)


@pytest.mark.parametrize("action", ACTIONS)
def test_each_action_uses_the_permission_of_the_spec(make_user, target, action):
    from django.contrib.auth.models import Permission

    actor = make_user("solo_un_permiso")
    actor.user_permissions.add(Permission.objects.get(codename=PERMISSIONS[action]))
    if action == "reactivate":
        target.is_active = False
        target.save()

    ACTIONS[action](User.objects.get(pk=actor.pk), target)
