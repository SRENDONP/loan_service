"""Modelo de usuario propio del proyecto (SPEC 03 y SPEC 04)."""

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager
from apps.accounts.validators import (
    UsernameValidator,
    colombian_mobile_validator,
    document_number_validator,
)


class DocumentType(models.TextChoices):
    """
    Tipos de documento del usuario (SPEC 04, §3.2).

    Son opciones fijas; la SPEC 06 decide si pasan al catálogo administrable.
    """

    CC = "CC", _("Cédula de ciudadanía")
    CE = "CE", _("Cédula de extranjería")
    PPT = "PPT", _("Permiso por protección temporal")
    PA = "PA", _("Pasaporte")
    TI = "TI", _("Tarjeta de identidad")


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
    phone = models.CharField(
        _("teléfono celular"),
        max_length=10,
        blank=True,
        validators=[colombian_mobile_validator],
    )
    document_type = models.CharField(
        _("tipo de documento"),
        max_length=3,
        choices=DocumentType.choices,
        blank=True,
    )
    document_number = models.CharField(
        _("número de documento"),
        max_length=20,
        blank=True,
        validators=[document_number_validator],
    )
    deactivated_at = models.DateTimeField(_("desactivado el"), null=True, blank=True)
    deactivated_by = models.ForeignKey(
        "self",
        verbose_name=_("desactivado por"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    deactivation_reason = models.TextField(
        _("motivo de desactivación"), max_length=500, blank=True
    )

    objects = UserManager()

    class Meta:
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")
        # Los usuarios nunca se borran, solo se desactivan (§6.3).
        default_permissions = ("add", "change", "view")
        permissions = [
            ("deactivate_user", _("Puede desactivar y reactivar usuarios")),
            ("unlock_user", _("Puede desbloquear usuarios")),
            (
                "reset_user_password",
                _("Puede restablecer la contraseña de otros usuarios"),
            ),
            (
                "logout_user_sessions",
                _("Puede cerrar las sesiones de otros usuarios"),
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_unique",
                violation_error_message=_("Ya existe un usuario con este correo."),
            ),
            models.CheckConstraint(
                condition=(
                    Q(document_type="", document_number="")
                    | (~Q(document_type="") & ~Q(document_number=""))
                ),
                name="accounts_user_document_complete",
                violation_error_message=_(
                    "Escribe el tipo y el número de documento, o deja los dos vacíos."
                ),
            ),
            models.UniqueConstraint(
                fields=["document_type", "document_number"],
                condition=~Q(document_number=""),
                name="accounts_user_document_unique",
                violation_error_message=_(
                    "Ya existe un usuario con este tipo y número de documento."
                ),
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.document_number = self.document_number.strip().upper()

    @property
    def status(self) -> str:
        """
        Estado para mostrar: `"inactive"`, `"locked"` o `"active"`, en ese orden.

        El bloqueo se calcula igual que `services.is_locked`, que no se importa
        aquí para no crear un ciclo entre el modelo y los servicios.
        """
        if not self.is_active:
            return "inactive"
        if self.locked_until is not None and self.locked_until > timezone.now():
            return "locked"
        return "active"
