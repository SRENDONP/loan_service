"""Pruebas del modelo de usuario propio (SPEC 03, §3.1)."""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_auth_user_model_is_accounts_user():
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert get_user_model() is User


def test_create_user_must_change_password():
    user = User.objects.create_user("cobrador", password="abc12345")

    assert user.must_change_password is True
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_create_superuser_does_not_need_to_change_password():
    user = User.objects.create_superuser("admin", "admin@example.com", "abc12345")

    assert user.must_change_password is False
    assert user.is_superuser is True


def test_email_is_unique_ignoring_case():
    User.objects.create_user("ana", email="ana@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("ana2", email="ANA@Example.com")


def test_email_unique_constraint_has_spanish_message_on_full_clean():
    User.objects.create_user("ana", email="ana@example.com")
    duplicate = User(username="ana2", email="Ana@example.com")
    duplicate.set_unusable_password()

    with pytest.raises(ValidationError) as excinfo:
        duplicate.full_clean()

    assert "Ya existe un usuario con este correo." in excinfo.value.messages


def test_several_users_without_email_are_allowed():
    User.objects.create_user("sin_correo_1")
    User.objects.create_user("sin_correo_2")

    assert User.objects.filter(email="").count() == 2


@pytest.mark.parametrize("username", ["ana@example.com", "ana+1", "ana perez"])
def test_username_rejects_invalid_characters(username):
    user = User(username=username)
    user.set_unusable_password()

    with pytest.raises(ValidationError) as excinfo:
        user.full_clean()

    assert "username" in excinfo.value.message_dict


@pytest.mark.parametrize("username", ["ana", "ana.perez", "ana_perez", "ana-1", "Ñoño"])
def test_username_accepts_letters_digits_dot_underscore_and_dash(username):
    user = User(username=username)
    user.set_unusable_password()

    user.full_clean()
