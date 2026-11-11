"""
Servicios de autenticación: búsqueda por usuario o correo y bloqueo temporal.

Todos los servicios que dependen de la hora reciben `now`, para poder probarlos
sin librerías de tiempo. Si es `None`, usan `timezone.now()`.

La segunda parte (SPEC 04, §3.5) es la gestión de usuarios: cada servicio recibe
al `actor`, verifica su permiso con `require_perms` y aplica las reglas de la
spec, aunque se llame sin pasar por una vista.

La SPEC 04 reutiliza `clear_failed_attempts` para desbloquear desde la
aplicación, y la SPEC 05 audita los ingresos desde aquí.
"""

import secrets
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.contrib.auth import SESSION_KEY, authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.accounts.permissions import require_perms
from apps.accounts.policy import (
    get_lockout_duration,
    get_max_failed_attempts,
    get_password_min_length,
)
from apps.accounts.roles import Role, get_role


def find_user_by_identifier(identifier: str) -> User | None:
    """
    Busca al usuario por correo si el texto contiene "@", o por nombre de usuario.

    El correo se compara sin distinguir mayúsculas; el nombre de usuario, exacto.
    Como el nombre de usuario no admite "@", nunca hay dos usuarios que coincidan.
    """
    if not identifier:
        return None
    if "@" in identifier:
        return User.objects.filter(email__iexact=identifier).first()
    return User.objects.filter(username=identifier).first()


def is_locked(user: User, now: datetime | None = None) -> bool:
    """La cuenta está bloqueada si `locked_until` es mayor que la hora actual."""
    now = now or timezone.now()
    return user.locked_until is not None and user.locked_until > now


def authenticate_with_lockout(
    request: HttpRequest | None,
    identifier: str,
    password: str,
    now: datetime | None = None,
) -> User | None:
    """
    Autentica aplicando el bloqueo temporal por cuenta.

    Durante el bloqueo, ni la contraseña correcta permite entrar ni el intento
    se cuenta. Un fallo con un usuario existente suma un intento; un ingreso
    correcto pone el contador en 0.
    """
    now = now or timezone.now()
    user = find_user_by_identifier(identifier)
    if user is not None and is_locked(user, now):
        return None

    authenticated = authenticate(
        request, username=identifier, password=password, now=now
    )
    if authenticated is None:
        if user is not None:
            register_failed_attempt(user, now)
        return None

    clear_failed_attempts(authenticated)
    return authenticated


def register_failed_attempt(user: User, now: datetime | None = None) -> None:
    """
    Suma un fallo seguido y bloquea la cuenta al llegar al máximo.

    Al bloquear, el contador vuelve a 0, así que al vencer el bloqueo ya está
    limpio. La fila se bloquea con `select_for_update()` para que dos intentos
    simultáneos no se pisen, y un intento que llega con la cuenta ya bloqueada
    no alarga el bloqueo.
    """
    now = now or timezone.now()
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if is_locked(locked, now):
            return
        locked.failed_login_attempts += 1
        if locked.failed_login_attempts >= get_max_failed_attempts():
            locked.locked_until = now + get_lockout_duration()
            locked.failed_login_attempts = 0
        locked.save(update_fields=["failed_login_attempts", "locked_until"])

    user.failed_login_attempts = locked.failed_login_attempts
    user.locked_until = locked.locked_until


def clear_failed_attempts(user: User) -> None:
    """Pone el contador de fallos en 0 y desbloquea la cuenta."""
    if user.failed_login_attempts == 0 and user.locked_until is None:
        return
    user.failed_login_attempts = 0
    user.locked_until = None
    user.save(update_fields=["failed_login_attempts", "locked_until"])


def mark_password_changed(user: User) -> None:
    """Apaga la marca de cambio obligatorio de contraseña."""
    if not user.must_change_password:
        return
    user.must_change_password = False
    user.save(update_fields=["must_change_password"])


# --- Gestión de usuarios (SPEC 04, §3.5) -----------------------------------

PROFILE_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "document_type",
    "document_number",
)
"""Datos del usuario que se pueden editar. `username` solo se fija al crear."""

TEMPORARY_PASSWORD_LENGTH = 12
# Letras y dígitos sin los que se confunden al dictarlos o leerlos.
TEMPORARY_PASSWORD_ALPHABET = "".join(
    char
    for char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    if char not in "0Oo1lI"
)


class UserRuleError(ValidationError):
    """Una regla de la gestión de usuarios impide la acción. Lleva el mensaje."""


def generate_temporary_password() -> str:
    """
    Contraseña temporal aleatoria que cumple la política de contraseñas.

    Tiene la mayor longitud entre 12 y la mínima de la política, solo letras y
    dígitos sin los ambiguos, y al menos una letra y un dígito. Se repite hasta
    que pase `validate_password`.
    """
    length = max(TEMPORARY_PASSWORD_LENGTH, get_password_min_length())
    while True:
        candidate = "".join(
            secrets.choice(TEMPORARY_PASSWORD_ALPHABET) for _ in range(length)
        )
        if not (
            any(char.isalpha() for char in candidate)
            and any(char.isdigit() for char in candidate)
        ):
            continue
        try:
            validate_password(candidate)
        except ValidationError:
            continue
        return candidate


def create_user(
    actor: User, *, data: Mapping[str, Any], role: Role
) -> tuple[User, str]:
    """
    Crea un usuario con su rol y una contraseña temporal.

    El usuario debe cambiar la contraseña en su primer ingreso. Devuelve el
    usuario y la contraseña en claro, que solo se muestra una vez.
    """
    require_perms(actor, "accounts.add_user")
    role = Role(role)
    password = generate_temporary_password()
    user = User(username=data.get("username", ""), must_change_password=True)
    _apply_profile(user, data)
    user.set_password(password)
    user.full_clean()
    with transaction.atomic():
        user.save()
        _set_role(user, role)
    return user, password


def update_user(
    actor: User, user: User, *, data: Mapping[str, Any], role: Role
) -> User:
    """
    Actualiza los datos y el rol de un usuario. Ignora `username`.

    Nadie cambia su propio rol, ningún superusuario se edita desde aquí y
    siempre queda al menos un administrador activo.
    """
    require_perms(actor, "accounts.change_user")
    role = Role(role)
    _ensure_not_superuser(user)
    current_role = get_role(user)
    if role != current_role:
        _ensure_not_self(actor, user, _("No puedes cambiar tu propio rol."))
    _apply_profile(user, data)
    user.full_clean()
    with transaction.atomic():
        if current_role == Role.ADMINISTRATOR and role != Role.ADMINISTRATOR:
            _ensure_another_administrator_remains(user)
        user.save()
        if role != current_role:
            _set_role(user, role)
    return user


DEACTIVATION_REASON_MAX_LENGTH = 500


def deactivate_user(actor: User, user: User, *, reason: str) -> None:
    """
    Desactiva al usuario con un motivo y cierra sus sesiones abiertas.

    Los usuarios nunca se borran (§6.3). Nadie se desactiva a sí mismo y
    siempre queda al menos un administrador activo.
    """
    require_perms(actor, "accounts.deactivate_user")
    _ensure_not_superuser(user)
    _ensure_not_self(actor, user, _("No puedes desactivar tu propia cuenta."))
    _ensure_active(user)
    reason = (reason or "").strip()
    if not reason:
        raise UserRuleError(
            _("Escribe el motivo de la desactivación."), code="reason_required"
        )
    if len(reason) > DEACTIVATION_REASON_MAX_LENGTH:
        raise UserRuleError(
            _("El motivo no puede tener más de %(max)d caracteres.")
            % {"max": DEACTIVATION_REASON_MAX_LENGTH},
            code="reason_too_long",
        )
    with transaction.atomic():
        _ensure_another_administrator_remains(user)
        user.is_active = False
        user.deactivated_at = timezone.now()
        user.deactivated_by = actor
        user.deactivation_reason = reason
        user.save(
            update_fields=[
                "is_active",
                "deactivated_at",
                "deactivated_by",
                "deactivation_reason",
            ]
        )
        _delete_sessions(user)


def reactivate_user(actor: User, user: User) -> None:
    """
    Reactiva al usuario y le exige cambiar la contraseña en su próximo ingreso.

    Vacía los campos de la desactivación; la auditoría (SPEC 05) conserva el
    historial.
    """
    require_perms(actor, "accounts.deactivate_user")
    _ensure_not_superuser(user)
    _ensure_not_self(actor, user, _("No puedes reactivar tu propia cuenta."))
    if user.is_active:
        raise UserRuleError(_("El usuario ya está activo."), code="already_active")
    user.is_active = True
    user.deactivated_at = None
    user.deactivated_by = None
    user.deactivation_reason = ""
    user.must_change_password = True
    with transaction.atomic():
        user.save(
            update_fields=[
                "is_active",
                "deactivated_at",
                "deactivated_by",
                "deactivation_reason",
                "must_change_password",
            ]
        )


def unlock_user(actor: User, user: User) -> None:
    """Quita el bloqueo temporal por intentos fallidos (SPEC 03)."""
    require_perms(actor, "accounts.unlock_user")
    _ensure_not_superuser(user)
    _ensure_not_self(actor, user, _("No puedes desbloquear tu propia cuenta."))
    _ensure_active(user)
    with transaction.atomic():
        clear_failed_attempts(user)


def reset_user_password(actor: User, user: User) -> str:
    """
    Asigna una contraseña temporal nueva y la devuelve en claro.

    El usuario queda desbloqueado, con sus sesiones cerradas y obligado a
    cambiar la contraseña en su próximo ingreso.
    """
    require_perms(actor, "accounts.reset_user_password")
    _ensure_not_superuser(user)
    _ensure_not_self(
        actor,
        user,
        _("Para cambiar tu propia contraseña usa la opción Cambiar contraseña."),
    )
    _ensure_active(user)
    password = generate_temporary_password()
    user.set_password(password)
    user.must_change_password = True
    user.failed_login_attempts = 0
    user.locked_until = None
    with transaction.atomic():
        user.save(
            update_fields=[
                "password",
                "must_change_password",
                "failed_login_attempts",
                "locked_until",
            ]
        )
        _delete_sessions(user)
    return password


def logout_user_sessions(actor: User, user: User) -> int:
    """Cierra todas las sesiones abiertas del usuario y devuelve cuántas cerró."""
    require_perms(actor, "accounts.logout_user_sessions")
    _ensure_not_superuser(user)
    _ensure_not_self(actor, user, _("No puedes cerrar tus propias sesiones aquí."))
    _ensure_active(user)
    with transaction.atomic():
        return _delete_sessions(user)


def _delete_sessions(user: User) -> int:
    """
    Borra las sesiones no vencidas del usuario.

    Recorre todas las sesiones vigentes porque Django no guarda el usuario en
    una columna propia. Es aceptable para el tamaño de un negocio (SPEC 04).
    """
    user_id = str(user.pk)
    keys = [
        session.session_key
        for session in Session.objects.filter(expire_date__gt=timezone.now())
        if session.get_decoded().get(SESSION_KEY) == user_id
    ]
    if keys:
        Session.objects.filter(session_key__in=keys).delete()
    return len(keys)


def _ensure_active(user: User) -> None:
    if not user.is_active:
        raise UserRuleError(
            _("El usuario está inactivo. Reactívalo antes de hacer esto."),
            code="inactive",
        )


def _apply_profile(user: User, data: Mapping[str, Any]) -> None:
    for field in PROFILE_FIELDS:
        if field in data:
            setattr(user, field, data[field] if data[field] is not None else "")


def _set_role(user: User, role: Role) -> None:
    """Deja al usuario con exactamente un grupo: el de su rol."""
    from django.contrib.auth.models import Group

    user.groups.set([Group.objects.get(name=role.value)])


def _ensure_not_superuser(user: User) -> None:
    if user.is_superuser:
        raise UserRuleError(
            _("Los superusuarios no se gestionan desde la aplicación."),
            code="superuser",
        )


def _ensure_not_self(actor: User, user: User, message: str) -> None:
    if actor.pk == user.pk:
        raise UserRuleError(message, code="self")


def _ensure_another_administrator_remains(user: User) -> None:
    """
    Impide dejar el negocio sin administradores activos (SPEC 04, regla 3).

    Bloquea las filas de los administradores activos para que dos cambios
    simultáneos no puedan dejar a ninguno. Debe llamarse dentro de una
    transacción.
    """
    administrators = list(
        User.objects.active_administrators()
        .select_for_update(of=("self",))
        .values_list("pk", flat=True)
    )
    if user.pk in administrators and len(administrators) <= 1:
        raise UserRuleError(
            _("Debe quedar al menos un administrador activo."),
            code="last_administrator",
        )
