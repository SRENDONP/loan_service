"""Validadores de la app de cuentas."""

from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext as _gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from apps.accounts.policy import get_password_min_length


@deconstructible
class UsernameValidator(RegexValidator):
    """
    Nombre de usuario con letras, números, ".", "_" y "-".

    No admite "@" ni "+": el login busca por correo cuando el texto contiene "@",
    así que ningún nombre de usuario puede confundirse con un correo (SPEC 03).
    """

    regex = r"^[\w.-]+\Z"
    message = _(
        "Escribe un nombre de usuario válido. Solo puede tener letras, números "
        'y los caracteres ".", "_" y "-".'
    )
    flags = 0


colombian_mobile_validator = RegexValidator(
    regex=r"^3\d{9}\Z",
    message=_(
        "Escribe un celular colombiano de 10 dígitos que empiece por 3, "
        "sin espacios ni guiones."
    ),
    code="invalid_mobile",
)
"""Celular colombiano: 10 dígitos que empiezan por 3 (SPEC 04, §3.2)."""

document_number_validator = RegexValidator(
    regex=r"^[A-Za-z0-9]{3,20}\Z",
    message=_(
        "Escribe un número de documento de 3 a 20 letras o dígitos, "
        "sin espacios ni puntos."
    ),
    code="invalid_document_number",
)
"""
Número de documento: de 3 a 20 letras o dígitos (SPEC 04, §3.2).

Acepta minúsculas porque el modelo lo pasa a mayúsculas en `clean()`, que corre
después de los validadores de campo.
"""


class PolicyMinimumLengthValidator:
    """
    Longitud mínima de la contraseña, leída de `policy.py` en cada uso.

    Reemplaza a `MinimumLengthValidator` de Django, que fija la longitud al
    arrancar, para que la SPEC 06 pueda cambiarla sin reiniciar.
    """

    def validate(self, password: str, user: Any = None) -> None:
        min_length = get_password_min_length()
        if len(password) < min_length:
            raise ValidationError(
                ngettext(
                    "La contraseña es muy corta. Debe tener al menos "
                    "%(min_length)d carácter.",
                    "La contraseña es muy corta. Debe tener al menos "
                    "%(min_length)d caracteres.",
                    min_length,
                ),
                code="password_too_short",
                params={"min_length": min_length},
            )

    def get_help_text(self) -> str:
        min_length = get_password_min_length()
        return ngettext(
            "Tu contraseña debe tener al menos %(min_length)d carácter.",
            "Tu contraseña debe tener al menos %(min_length)d caracteres.",
            min_length,
        ) % {"min_length": min_length}


class LettersAndDigitsValidator:
    """La contraseña debe tener al menos una letra y al menos un número."""

    def validate(self, password: str, user: Any = None) -> None:
        has_letter = any(char.isalpha() for char in password)
        has_digit = any(char.isdigit() for char in password)
        if not (has_letter and has_digit):
            raise ValidationError(
                _gettext("La contraseña debe tener al menos una letra y un número."),
                code="password_letters_and_digits",
            )

    def get_help_text(self) -> str:
        return _gettext("Tu contraseña debe tener al menos una letra y un número.")
