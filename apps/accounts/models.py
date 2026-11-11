"""Modelo de usuario propio del proyecto (SPEC 03)."""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager
from apps.accounts.validators import UsernameValidator


class User(AbstractUser):
    """
    Usuario del sistema.

    El correo es opcional, pero si existe es único sin distinguir mayúsculas.
    La cuenta está bloqueada mientras `locked_until` sea mayor que la hora
    actual; la lógica del bloqueo vive en `apps.accounts.services`.
    """

    username_validator = UsernameValidator()

    # Se redefine porque el campo de AbstractUser toma el validador de Django
    # (que admite "@" y "+") al definirse la clase.
    username = models.CharField(
        _("nombre de usuario"),
        max_length=150,
        unique=True,
        help_text=_(
            'Obligatorio. Hasta 150 caracteres: letras, números, ".", "_" y "-".'
        ),
        validators=[username_validator],
        error_messages={
            "unique": _("Ya existe un usuario con este nombre de usuario."),
        },
    )
    email = models.EmailField(_("correo electrónico"), blank=True)
    must_change_password = models.BooleanField(
        _("debe cambiar la contraseña"), default=True
    )
    failed_login_attempts = models.PositiveSmallIntegerField(
        _("intentos fallidos seguidos"), default=0
    )
    locked_until = models.DateTimeField(_("bloqueado hasta"), null=True, blank=True)

    objects = UserManager()

    class Meta:
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_unique",
                violation_error_message=_("Ya existe un usuario con este correo."),
            ),
        ]
