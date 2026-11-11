"""
Servicio provisional de políticas de cuentas (SPEC 03, §3.2).

Es el único lugar que lee los valores del bloqueo, la longitud mínima de la
contraseña y la vigencia del enlace de recuperación. Hoy salen de los settings;
la SPEC 06 (parámetros globales) cambia solo este módulo para leerlos de la base
de datos, con el mismo patrón del context processor `branding` (ADR-001).

Las funciones se consultan en cada uso, nunca al arrancar, para que un cambio
del valor aplique sin reiniciar.
"""

from datetime import timedelta

from django.conf import settings

DEFAULT_MAX_FAILED_ATTEMPTS = 5
DEFAULT_LOCKOUT_MINUTES = 15
DEFAULT_PASSWORD_MIN_LENGTH = 8
DEFAULT_PASSWORD_RESET_TIMEOUT = 60 * 60


def get_max_failed_attempts() -> int:
    """Fallos seguidos que bloquean la cuenta."""
    return getattr(
        settings, "ACCOUNTS_MAX_FAILED_ATTEMPTS", DEFAULT_MAX_FAILED_ATTEMPTS
    )


def get_lockout_duration() -> timedelta:
    """Tiempo que dura el bloqueo temporal de la cuenta."""
    minutes = getattr(settings, "ACCOUNTS_LOCKOUT_MINUTES", DEFAULT_LOCKOUT_MINUTES)
    return timedelta(minutes=minutes)


def get_password_min_length() -> int:
    """Longitud mínima de la contraseña."""
    return getattr(
        settings, "ACCOUNTS_PASSWORD_MIN_LENGTH", DEFAULT_PASSWORD_MIN_LENGTH
    )


def get_password_reset_timeout() -> int:
    """Segundos que dura el enlace de recuperación de contraseña."""
    return getattr(settings, "PASSWORD_RESET_TIMEOUT", DEFAULT_PASSWORD_RESET_TIMEOUT)
