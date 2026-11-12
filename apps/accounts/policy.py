"""
Políticas de cuentas (SPEC 03, §3.2; SPEC 06, §3.4).

Es el único lugar de `accounts` que lee los valores del bloqueo, la longitud
mínima de la contraseña y la vigencia del enlace de recuperación. Desde la
SPEC 06 salen del registro de parámetros globales, por medio de su servicio
(ADR-001). Las funciones conservan el nombre y la firma de la SPEC 03.

Se consultan en cada uso, nunca al arrancar, para que un cambio del valor
aplique sin reiniciar.
"""

from datetime import timedelta

from apps.parametros.services import get_settings


def get_max_failed_attempts() -> int:
    """Fallos seguidos que bloquean la cuenta."""
    return get_settings().max_failed_attempts


def get_lockout_duration() -> timedelta:
    """Tiempo que dura el bloqueo temporal de la cuenta."""
    return timedelta(minutes=get_settings().lockout_minutes)


def get_password_min_length() -> int:
    """Longitud mínima de la contraseña."""
    return get_settings().password_min_length


def get_password_reset_timeout() -> int:
    """Segundos que dura el enlace de recuperación de contraseña."""
    return get_settings().password_reset_timeout_minutes * 60


def get_session_idle_timeout() -> timedelta:
    """Tiempo sin actividad que cierra la sesión (SPEC 06, §3.5)."""
    return timedelta(minutes=get_settings().session_idle_timeout_minutes)


def get_session_max_duration() -> timedelta:
    """Duración máxima de la sesión, aunque haya actividad (SPEC 06, §3.5)."""
    return timedelta(hours=get_settings().session_max_hours)
