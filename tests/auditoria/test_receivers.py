"""Pruebas de la auditoría de accesos por señales (SPEC 05, §3.7)."""

import pytest
from django.contrib.auth import authenticate
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.urls import reverse

from apps.auditoria import receivers
from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.models import AuditEvent, AuditSource

pytestmark = pytest.mark.django_db

LOGIN = reverse("accounts:login")
LOGOUT = reverse("accounts:logout")


def post_login(client, username: str, password: str):
    return client.post(
        LOGIN,
        {"username": username, "password": password},
        REMOTE_ADDR="10.0.0.7",
        HTTP_USER_AGENT="Navegador/1.0",
    )


def events(action: AuditAction):
    return list(AuditEvent.objects.filter(action=action).order_by("id"))


@pytest.mark.parametrize(
    ("signal", "dispatch_uid"),
    [
        (user_logged_in, "auditoria.login_succeeded"),
        (user_login_failed, "auditoria.login_failed"),
        (user_logged_out, "auditoria.logout"),
    ],
)
def test_receivers_are_connected_once(signal, dispatch_uid):
    # Cada entrada empieza por su clave: (dispatch_uid, id del emisor).
    keys = [entry[0] for entry in signal.receivers]

    assert [key[0] for key in keys].count(dispatch_uid) == 1


def test_successful_login_is_recorded(client, user, password):
    response = post_login(client, "cobrador", password)

    assert response.status_code == 302
    [event] = events(AuditAction.LOGIN_SUCCEEDED)
    assert event.category == AuditCategory.ACCESS
    assert event.actor == user
    assert event.actor_username == "cobrador"
    assert event.object_id == str(user.pk)
    assert event.ip_address == "10.0.0.7"
    assert event.user_agent == "Navegador/1.0"
    assert event.source == AuditSource.WEB
    assert event.request_path == LOGIN
    assert not events(AuditAction.LOGIN_FAILED)


def test_login_by_email_is_recorded_with_the_user(client, make_user, password):
    user = make_user("ana", email="ana@example.com")

    post_login(client, "ANA@example.com", password)

    [event] = events(AuditAction.LOGIN_SUCCEEDED)
    assert event.actor == user


def test_wrong_password_is_recorded(client, user):
    post_login(client, "cobrador", "incorrecta1")

    [event] = events(AuditAction.LOGIN_FAILED)
    assert event.actor is None
    assert event.actor_username == ""
    assert event.identifier == "cobrador"
    assert event.object_id == str(user.pk)
    assert event.object_repr == "cobrador"
    assert event.ip_address == "10.0.0.7"
    assert not events(AuditAction.LOGIN_SUCCEEDED)


def test_unknown_user_is_recorded_without_target(client):
    typed = "n" * 200

    post_login(client, typed, "incorrecta1")

    [event] = events(AuditAction.LOGIN_FAILED)
    assert event.actor is None
    assert event.content_type is None
    assert event.object_id == ""
    assert event.identifier == typed[:150]


def test_failed_login_never_stores_the_password(client, user):
    post_login(client, "cobrador", "MiClaveSecreta99")

    event = AuditEvent.objects.get(action=AuditAction.LOGIN_FAILED)
    stored = f"{event.changes}{event.extra}{event.identifier}{event.object_repr}"
    assert "MiClaveSecreta99" not in stored


def test_inactive_user_login_is_recorded_as_failed(client, make_user, password):
    make_user("inactivo", is_active=False)

    post_login(client, "inactivo", password)

    [event] = events(AuditAction.LOGIN_FAILED)
    assert event.identifier == "inactivo"


def test_failed_authenticate_outside_a_request_has_system_source(user):
    authenticate(None, username="cobrador", password="incorrecta1")

    [event] = events(AuditAction.LOGIN_FAILED)
    assert event.source == AuditSource.SYSTEM
    assert event.ip_address is None


def test_logout_is_recorded(client, user, password):
    post_login(client, "cobrador", password)

    client.post(LOGOUT)

    [event] = events(AuditAction.LOGOUT)
    assert event.category == AuditCategory.ACCESS
    assert event.actor == user
    assert event.object_id == str(user.pk)
    assert event.request_path == LOGOUT


def test_login_and_logout_have_different_request_ids(client, user, password):
    post_login(client, "cobrador", password)
    client.post(LOGOUT)

    [login] = events(AuditAction.LOGIN_SUCCEEDED)
    [logout] = events(AuditAction.LOGOUT)
    assert login.request_id != logout.request_id


def test_logout_without_session_is_not_recorded(client):
    client.post(LOGOUT)

    assert not events(AuditAction.LOGOUT)


def test_logout_receiver_ignores_missing_user():
    receivers.audit_logout(sender=None, request=None, user=None)

    assert not AuditEvent.objects.exists()


def test_login_failed_receiver_without_username():
    receivers.audit_login_failed(sender=None, credentials={"password": "****"})

    [event] = events(AuditAction.LOGIN_FAILED)
    assert event.identifier == ""
    assert event.content_type is None
