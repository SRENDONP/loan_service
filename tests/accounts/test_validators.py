"""Pruebas de la política de contraseñas (SPEC 03, §2 y paso 3)."""

import pytest
from django.contrib.auth.password_validation import (
    password_validators_help_texts,
    validate_password,
)
from django.core.exceptions import ValidationError

from apps.accounts.validators import (
    LettersAndDigitsValidator,
    PolicyMinimumLengthValidator,
)

# La longitud mínima sale de los parámetros globales (SPEC 06).
pytestmark = pytest.mark.django_db


def validation_messages(password: str) -> list[str]:
    """Mensajes de error de toda la cadena de validadores del proyecto."""
    with pytest.raises(ValidationError) as excinfo:
        validate_password(password)
    return excinfo.value.messages


def test_valid_password_passes_all_validators():
    validate_password("cobro2026")


def test_password_without_digits_is_rejected():
    assert (
        "La contraseña debe tener al menos una letra y un número."
        in validation_messages("abcdefgh")
    )


def test_password_without_letters_is_rejected():
    assert (
        "La contraseña debe tener al menos una letra y un número."
        in validation_messages("12345678")
    )


def test_short_password_is_rejected():
    assert (
        "La contraseña es muy corta. Debe tener al menos 8 caracteres."
        in validation_messages("abc1234")
    )


def test_common_password_is_rejected():
    # "abc12345" cumple la longitud y tiene letras y números, pero está en la
    # lista de contraseñas comunes de Django.
    assert validation_messages("abc12345")


def test_messages_are_in_spanish():
    messages = validation_messages("12345678")

    assert "Esta contraseña es demasiado común." in messages
    assert "Esta contraseña es completamente numérica." in messages


def test_min_length_follows_policy(global_settings):
    global_settings.password_min_length = 12
    global_settings.save()
    messages = validation_messages("cobro2026")

    assert "La contraseña es muy corta. Debe tener al menos 12 caracteres." in messages


def test_password_at_policy_length_is_accepted(global_settings):
    # El mínimo del parámetro es 8 (SPEC 06, §3.2); se prueba el borde con 10.
    global_settings.password_min_length = 10
    global_settings.save()

    PolicyMinimumLengthValidator().validate("cobro20261")
    with pytest.raises(ValidationError):
        PolicyMinimumLengthValidator().validate("cobro2026")


def test_help_texts_are_in_spanish():
    help_texts = password_validators_help_texts()

    assert "Tu contraseña debe tener al menos 8 caracteres." in help_texts
    assert "Tu contraseña debe tener al menos una letra y un número." in help_texts


def test_min_length_help_text_follows_policy(global_settings):
    global_settings.password_min_length = 10
    global_settings.save()
    assert (
        PolicyMinimumLengthValidator().get_help_text()
        == "Tu contraseña debe tener al menos 10 caracteres."
    )


@pytest.mark.parametrize("password", ["cobro2026", "ñandú7", "Prestamo1"])
def test_letters_and_digits_accepts_mixed_passwords(password):
    LettersAndDigitsValidator().validate(password)
