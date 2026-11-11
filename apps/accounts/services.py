"""
Servicios de autenticación: búsqueda por usuario o correo y bloqueo temporal.

Todos los servicios que dependen de la hora reciben `now`, para poder probarlos
sin librerías de tiempo. Si es `None`, usan `timezone.now()`.

La SPEC 04 reutiliza `clear_failed_attempts` para desbloquear desde la
aplicación, y la SPEC 05 audita los ingresos desde aquí.
"""

from datetime import datetime

from django.contrib.auth import authenticate
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.policy import get_lockout_duration, get_max_failed_attempts


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
