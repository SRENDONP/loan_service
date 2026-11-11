"""Pruebas del backend UsernameOrEmailBackend (SPEC 03, paso 4)."""

from datetime import timedelta

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth import authenticate
from django.utils import timezone

from apps.accounts.backends import UsernameOrEmailBackend

pytestmark = pytest.mark.django_db


def test_authenticates_with_username(make_user, password):
    user = make_user("ana", email="ana@example.com")

    assert authenticate(None, username="ana", password=password) == user


def test_authenticates_with_email(make_user, password):
    user = make_user("ana", email="ana@example.com")

    assert authenticate(None, username="ana@example.com", password=password) == user


def test_authenticates_with_email_in_other_case(make_user, password):
    user = make_user("ana", email="ana@example.com")

    assert authenticate(None, username="ANA@Example.COM", password=password) == user


def test_username_is_case_sensitive(make_user, password):
    make_user("ana")

    assert authenticate(None, username="ANA", password=password) is None


def test_wrong_password_is_rejected(make_user):
    make_user("ana")

    assert authenticate(None, username="ana", password="otra2026") is None


def test_inactive_user_is_rejected(make_user, password):
    make_user("ana", is_active=False)

    assert authenticate(None, username="ana", password=password) is None


def test_unknown_user_is_rejected(password):
    assert authenticate(None, username="nadie", password=password) is None
    assert authenticate(None, username="nadie@example.com", password=password) is None


def test_missing_credentials_are_rejected(make_user, password):
    make_user("ana")

    assert authenticate(None, username="ana") is None
    assert UsernameOrEmailBackend().authenticate(None, password=password) is None


def test_locked_user_is_rejected_with_correct_password(make_user, password):
    make_user("ana", locked_until=timezone.now() + timedelta(minutes=5))

    assert authenticate(None, username="ana", password=password) is None


def test_lock_is_evaluated_at_the_given_now(make_user, password):
    now = timezone.now()
    user = make_user("ana", locked_until=now + timedelta(minutes=15))

    backend = UsernameOrEmailBackend()
    assert backend.authenticate(None, "ana", password, now=now) is None
    assert (
        backend.authenticate(None, "ana", password, now=now + timedelta(minutes=15))
        == user
    )


def test_user_can_authenticate_rejects_inactive_and_locked(make_user):
    backend = UsernameOrEmailBackend()

    assert backend.user_can_authenticate(make_user("activo")) is True
    assert (
        backend.user_can_authenticate(make_user("inactivo", is_active=False)) is False
    )
    locked = make_user("bloqueado", locked_until=timezone.now() + timedelta(minutes=5))
    assert backend.user_can_authenticate(locked) is False


def test_get_user_keeps_locked_user_and_rejects_inactive(make_user):
    backend = UsernameOrEmailBackend()
    locked = make_user("bloqueado", locked_until=timezone.now() + timedelta(minutes=5))
    inactive = make_user("inactivo", is_active=False)

    assert backend.get_user(locked.pk) == locked
    assert backend.get_user(inactive.pk) is None
    assert backend.get_user(999_999) is None


def test_open_session_survives_lockout(client, make_user):
    user = make_user("ana")
    client.force_login(user)
    user.locked_until = timezone.now() + timedelta(minutes=15)
    user.save(update_fields=["locked_until"])

    response = client.get("/health/")

    assert response.wsgi_request.user == user


def test_async_authenticate_also_accepts_email(make_user, password):
    user = make_user("ana", email="ana@example.com")
    backend = UsernameOrEmailBackend()

    result = async_to_sync(backend.aauthenticate)(
        None, username="ana@example.com", password=password
    )

    assert result == user
