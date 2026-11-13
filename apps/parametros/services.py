"""
Servicio de parámetros globales (SPEC 06, §3.3, ADR-001), catálogos y festivos
(SPEC 07, §3.6).

Es la única forma de leer los parámetros: vistas, plantillas, `policy.py` y
`branding` pasan por aquí. Así, el día que haya varios negocios, solo cambia
este módulo, que pasaría a recibir el negocio activo.

No hay caché: la fila se consulta en cada uso, para que un cambio aplique en la
siguiente petición en todos los procesos sin reiniciar.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import QuerySet
from django.utils.translation import gettext as _

from apps.auditoria.actions import AuditAction
from apps.auditoria.services import diff, record, snapshot
from apps.parametros.catalogs import Catalog
from apps.parametros.holidays import colombian_holidays
from apps.parametros.models import (
    SINGLETON_PK,
    CatalogItem,
    GlobalSettings,
    Holiday,
    HolidayOrigin,
    RoundingMode,
)

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
    Si `day` es un día hábil (SPEC 07, §3.6).

    No lo es si su día de la semana está en `non_business_weekdays` o si hay un
    festivo activo, oficial o propio, en esa fecha. Un año sin festivos
    cargados solo descarta los días de la semana.
    """
    if day.isoweekday() in get_settings().non_business_weekdays:
        return False
    return not Holiday.objects.filter(date=day, is_active=True).exists()


# Catálogos y festivos: lectura (SPEC 07, §3.6). No piden permisos.


def get_active_items[T: CatalogItem](model: type[T]) -> QuerySet[T]:
    """Los ítems activos del catálogo, en el orden de `display_order` y `name`."""
    return model.objects.active()


def get_item_by_code[T: CatalogItem](model: type[T], code: str) -> T:
    """El ítem con ese código, activo o no. Lanza `model.DoesNotExist`."""
    return model.objects.get(code=code)


def get_holidays(start: date, end: date) -> frozenset[date]:
    """
    Las fechas de los festivos activos entre `start` y `end`, incluidos.

    Son de los dos orígenes. Es la lista de fechas que recibe el calendario del
    motor. Lanza `ValueError` si `start` es posterior a `end`.
    """
    if start > end:
        raise ValueError("La fecha de inicio es posterior a la de fin.")
    return frozenset(
        Holiday.objects.filter(date__range=(start, end), is_active=True).values_list(
            "date", flat=True
        )
    )


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


# Catálogos y festivos: edición (SPEC 07, §3.6 y §3.8)

# Campos que se auditan y campos que cada servicio de edición puede tocar.
CATALOG_AUDIT_FIELDS = ("code", "name", "display_order", "is_active")
CATALOG_EDIT_FIELDS = ("name", "display_order")
HOLIDAY_AUDIT_FIELDS = ("date", "name", "origin", "is_active")
HOLIDAY_EDIT_FIELDS = ("date", "name")

CODE_MAX_LENGTH = 30


class CatalogRuleError(ValidationError):
    """Una regla de los catálogos o los festivos impide la acción. Lleva el mensaje."""


def _require(actor: User, model: type[models.Model], action: str) -> None:
    """Verifica `parametros.<action>_<modelo>`; lanza `PermissionDenied` sin él."""
    # Importación local por el ciclo con `accounts.policy` (SPEC 06, §6.1).
    from apps.accounts.permissions import require_perms

    meta = model._meta
    require_perms(actor, f"{meta.app_label}.{action}_{meta.model_name}")


def generate_code(model: type[CatalogItem], name: str) -> str:
    """
    Un código libre en `model` a partir del nombre (SPEC 07, §3.1).

    Mayúsculas sin tildes, y los espacios y signos pasan a `_`: "Pago de
    arriendo" da `PAGO_DE_ARRIENDO`. Si ese código ya existe, agrega `_2`, `_3`
    y así, sin pasar del largo del campo.
    """
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    base = re.sub(r"[^A-Z0-9]+", "_", ascii_name.upper()).strip("_")
    base = base[:CODE_MAX_LENGTH] or "ITEM"
    code, number = base, 2
    while model.objects.filter(code=code).exists():
        suffix = f"_{number}"
        code = base[: CODE_MAX_LENGTH - len(suffix)] + suffix
        number += 1
    return code


def create_catalog_item(
    actor: User, catalog: Catalog, data: Mapping[str, Any]
) -> CatalogItem:
    """
    Crea un ítem en el catálogo. Si `data` no trae código, lo genera del nombre.

    `is_system` y `is_active` en `data` se ignoran: un ítem nuevo es activo y
    no es de sistema. Lanza `ValidationError` con los errores por campo.
    """
    model = catalog.model
    _require(actor, model, "add")

    name = str(data.get("name") or "").strip()
    code = str(data.get("code") or "").strip()
    if not code and name:
        code = generate_code(model, name)
    item = model(
        code=code,
        name=name,
        display_order=data.get("display_order") or 0,
        updated_by=actor,
    )
    with transaction.atomic():
        item.full_clean()
        item.save()
        record(
            AuditAction.CATALOG_ITEM_CREATED,
            actor=actor,
            target=item,
            changes=diff({}, snapshot(item, CATALOG_AUDIT_FIELDS)),
        )
    return item


def update_catalog_item[T: CatalogItem](
    actor: User, item: T, data: Mapping[str, Any]
) -> T:
    """
    Edita el nombre y el orden del ítem. El código, el estado y `is_system` no
    cambian aunque vengan en `data`. Sin cambios no guarda ni registra.
    """
    model = type(item)
    _require(actor, model, "change")
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=item.pk)
        before = snapshot(locked, CATALOG_AUDIT_FIELDS)
        for name in CATALOG_EDIT_FIELDS:
            if name in data:
                setattr(locked, name, data[name])
        locked.full_clean()
        changes = diff(before, snapshot(locked, CATALOG_AUDIT_FIELDS))
        if not changes:
            return locked
        locked.updated_by = actor
        locked.save()
        record(
            AuditAction.CATALOG_ITEM_UPDATED,
            actor=actor,
            target=locked,
            changes=changes,
        )
    return locked


def deactivate_catalog_item[T: CatalogItem](actor: User, item: T) -> T:
    """Desactiva el ítem. Lanza `CatalogRuleError` si es de sistema o ya inactivo."""
    model = type(item)
    _require(actor, model, "change")
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=item.pk)
        if locked.is_system:
            raise CatalogRuleError(_("Un ítem de sistema no se puede desactivar."))
        if not locked.is_active:
            raise CatalogRuleError(_("El ítem ya está inactivo."))
        _set_active(locked, False, actor, AuditAction.CATALOG_ITEM_DEACTIVATED)
    return locked


def reactivate_catalog_item[T: CatalogItem](actor: User, item: T) -> T:
    """Reactiva el ítem. Lanza `CatalogRuleError` si ya está activo."""
    model = type(item)
    _require(actor, model, "change")
    with transaction.atomic():
        locked = model.objects.select_for_update().get(pk=item.pk)
        if locked.is_active:
            raise CatalogRuleError(_("El ítem ya está activo."))
        _set_active(locked, True, actor, AuditAction.CATALOG_ITEM_REACTIVATED)
    return locked


def create_holiday(actor: User, data: Mapping[str, Any]) -> Holiday:
    """
    Crea un festivo propio con `date` y `name`. Los oficiales solo los crea la
    carga. Lanza `ValidationError` si la fecha ya tiene un festivo activo.
    """
    _require(actor, Holiday, "add")
    holiday = Holiday(
        date=data.get("date"),
        name=str(data.get("name") or ""),
        origin=HolidayOrigin.CUSTOM,
        updated_by=actor,
    )
    with transaction.atomic():
        holiday.full_clean()
        holiday.save()
        record(
            AuditAction.HOLIDAY_CREATED,
            actor=actor,
            target=holiday,
            changes=diff({}, snapshot(holiday, HOLIDAY_AUDIT_FIELDS)),
        )
    return holiday


def update_holiday(actor: User, holiday: Holiday, data: Mapping[str, Any]) -> Holiday:
    """
    Edita la fecha y el nombre. Un festivo oficial conserva su origen, su
    código y su año. Sin cambios no guarda ni registra.
    """
    _require(actor, Holiday, "change")
    with transaction.atomic():
        locked = Holiday.objects.select_for_update().get(pk=holiday.pk)
        before = snapshot(locked, HOLIDAY_AUDIT_FIELDS)
        for name in HOLIDAY_EDIT_FIELDS:
            if name in data:
                setattr(locked, name, data[name])
        locked.full_clean()
        changes = diff(before, snapshot(locked, HOLIDAY_AUDIT_FIELDS))
        if not changes:
            return locked
        locked.updated_by = actor
        locked.save()
        record(AuditAction.HOLIDAY_UPDATED, actor=actor, target=locked, changes=changes)
    return locked


def deactivate_holiday(actor: User, holiday: Holiday) -> Holiday:
    """Desactiva el festivo. Lanza `CatalogRuleError` si ya está inactivo."""
    _require(actor, Holiday, "change")
    with transaction.atomic():
        locked = Holiday.objects.select_for_update().get(pk=holiday.pk)
        if not locked.is_active:
            raise CatalogRuleError(_("El festivo ya está inactivo."))
        _set_active(locked, False, actor, AuditAction.HOLIDAY_DEACTIVATED)
    return locked


def reactivate_holiday(actor: User, holiday: Holiday) -> Holiday:
    """
    Reactiva el festivo. Lanza `CatalogRuleError` si ya está activo y
    `ValidationError` si su fecha ya tiene otro festivo activo.
    """
    _require(actor, Holiday, "change")
    with transaction.atomic():
        locked = Holiday.objects.select_for_update().get(pk=holiday.pk)
        if locked.is_active:
            raise CatalogRuleError(_("El festivo ya está activo."))
        _set_active(locked, True, actor, AuditAction.HOLIDAY_REACTIVATED)
    return locked


def _set_active(
    instance: CatalogItem | Holiday,
    active: bool,
    actor: User,
    action: AuditAction,
) -> None:
    """Cambia el estado, valida, guarda y audita. Va dentro de la transacción."""
    fields = (
        HOLIDAY_AUDIT_FIELDS
        if isinstance(instance, Holiday)
        else (CATALOG_AUDIT_FIELDS)
    )
    before = snapshot(instance, fields)
    instance.is_active = active
    instance.full_clean()
    instance.updated_by = actor
    instance.save()
    record(
        action,
        actor=actor,
        target=instance,
        changes=diff(before, snapshot(instance, fields)),
    )


def load_official_holidays(year: int, *, actor: User | None = None) -> int:
    """
    Crea los festivos oficiales de `year` que falten y devuelve cuántos creó.

    Un festivo oficial se reconoce por `official_year` y `official_code`: si ya
    existe, no se toca, aunque esté desactivado o con otra fecha. Si la fecha ya
    tiene un festivo activo, el nuevo se crea desactivado. Si creó alguno,
    audita una sola vez. Sin actor (el comando) no verifica permisos; con actor,
    exige `parametros.add_holiday`. Lanza `ValueError` fuera de 1984 a 2100.
    """
    if actor is not None:
        _require(actor, Holiday, "add")
    officials = colombian_holidays(year)

    created = 0
    with transaction.atomic():
        existing = set(
            Holiday.objects.select_for_update()
            .filter(origin=HolidayOrigin.OFFICIAL, official_year=year)
            .values_list("official_code", flat=True)
        )
        for official in officials:
            if official.code in existing:
                continue
            taken = Holiday.objects.filter(date=official.date, is_active=True).exists()
            Holiday.objects.create(
                date=official.date,
                name=official.name,
                origin=HolidayOrigin.OFFICIAL,
                official_code=official.code,
                official_year=year,
                is_active=not taken,
                updated_by=actor,
            )
            created += 1
        if created:
            record(
                AuditAction.HOLIDAYS_LOADED,
                actor=actor,
                extra={"year": year, "created": created},
            )
    return created


def missing_official_years(years: Iterable[int]) -> list[int]:
    """De `years`, los que no tienen ningún festivo oficial, en el mismo orden."""
    years = list(years)
    loaded = set(
        Holiday.objects.filter(
            origin=HolidayOrigin.OFFICIAL, official_year__in=years
        ).values_list("official_year", flat=True)
    )
    return [year for year in years if year not in loaded]
