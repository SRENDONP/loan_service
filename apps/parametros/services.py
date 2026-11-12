"""
Servicio de parámetros globales (SPEC 06, §3.3, ADR-001).

Es la única forma de leer los parámetros: vistas, plantillas, `policy.py` y
`branding` pasan por aquí. Así, el día que haya varios negocios, solo cambia
este módulo, que pasaría a recibir el negocio activo.

No hay caché: la fila se consulta en cada uso, para que un cambio aplique en la
siguiente petición en todos los procesos sin reiniciar.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.auditoria.actions import AuditAction
from apps.auditoria.services import diff, record, snapshot
from apps.parametros.models import SINGLETON_PK, GlobalSettings, RoundingMode

if TYPE_CHECKING:
    from apps.accounts.models import User

CHANGE_PERMISSION = "parametros.change_globalsettings"

# Campos de cada grupo (SPEC 06, §2). Cada servicio de edición solo toca los
# campos de su grupo.
BUSINESS_FIELDS = (
    "business_name",
    "brand_icon",
    "currency_code",
    "currency_symbol",
    "currency_decimals",
    "date_format",
)
COLLECTION_FIELDS = (
    "collection_weekdays",
    "collection_start_time",
    "collection_end_time",
    "non_business_weekdays",
    "holiday_shift_rule",
)
ROUNDING_FIELDS = ("rounding_multiple", "rounding_mode")
SECURITY_FIELDS = (
    "max_failed_attempts",
    "lockout_minutes",
    "password_min_length",
    "password_reset_timeout_minutes",
    "session_idle_timeout_minutes",
    "session_max_hours",
)


@dataclass(frozen=True)
class RoundingRule:
    """Regla de redondeo por defecto. El motor la recibe como parámetro."""

    multiple: Decimal
    mode: RoundingMode


def get_settings() -> GlobalSettings:
    """
    La fila única de parámetros.

    Si no existe (por ejemplo, después de un `flush` en las pruebas), la crea
    con los valores por defecto.
    """
    settings, _ = GlobalSettings.objects.get_or_create(pk=SINGLETON_PK)
    return settings


def get_rounding_rule() -> RoundingRule:
    """El múltiplo como `Decimal` y el modo del redondeo por defecto."""
    settings = get_settings()
    return RoundingRule(
        multiple=Decimal(settings.rounding_multiple),
        mode=RoundingMode(settings.rounding_mode),
    )


def is_business_day(day: date) -> bool:
    """
    Si `day` es un día hábil.

    Por ahora solo mira los días de la semana no hábiles. La SPEC 07 agrega los
    festivos sin cambiar la firma.
    """
    return day.isoweekday() not in get_settings().non_business_weekdays


# Edición


def update_business(actor: User, data: Mapping[str, Any]) -> GlobalSettings:
    """Edita el nombre, el icono, la moneda y el formato de fecha."""
    return _update(actor, data, BUSINESS_FIELDS, AuditAction.SETTINGS_BUSINESS_UPDATED)


def update_collection(actor: User, data: Mapping[str, Any]) -> GlobalSettings:
    """Edita los días y el horario de cobro, los días no hábiles y el corrimiento."""
    return _update(
        actor, data, COLLECTION_FIELDS, AuditAction.SETTINGS_COLLECTION_UPDATED
    )


def update_rounding(actor: User, data: Mapping[str, Any]) -> GlobalSettings:
    """Edita el múltiplo y el modo del redondeo por defecto."""
    return _update(actor, data, ROUNDING_FIELDS, AuditAction.SETTINGS_ROUNDING_UPDATED)


def update_security(actor: User, data: Mapping[str, Any]) -> GlobalSettings:
    """Edita el bloqueo, la contraseña, el enlace de recuperación y la sesión."""
    return _update(actor, data, SECURITY_FIELDS, AuditAction.SETTINGS_SECURITY_UPDATED)


def _update(
    actor: User,
    data: Mapping[str, Any],
    fields: tuple[str, ...],
    action: AuditAction,
) -> GlobalSettings:
    """
    Asigna solo los campos del grupo, valida, guarda y audita.

    Un dato de otro grupo en `data` se ignora, y un campo del grupo que no
    viene en `data` conserva su valor. Si nada cambió, no guarda ni registra.
    Lanza `PermissionDenied` sin el permiso y `ValidationError` con los errores
    por campo. Si `record` falla, la fila no cambia.
    """
    # Importación local: `accounts.policy` importa este módulo mientras se
    # cargan los modelos de `accounts`, y `permissions` necesita el modelo de
    # usuario ya cargado (SPEC 06, §7).
    from apps.accounts.permissions import require_perms

    require_perms(actor, CHANGE_PERMISSION)
    get_settings()  # Garantiza que la fila exista antes de bloquearla.
    with transaction.atomic():
        settings = GlobalSettings.objects.select_for_update().get(pk=SINGLETON_PK)
        before = snapshot(settings, fields)
        for name in fields:
            if name in data:
                setattr(settings, name, data[name])
        settings.full_clean()
        changes = diff(before, snapshot(settings, fields))
        if not changes:
            return settings
        settings.updated_by = actor
        settings.save()
        record(action, actor=actor, target=settings, changes=changes)
    return settings
