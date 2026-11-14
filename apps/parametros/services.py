"""
Servicio de parámetros globales (SPEC 06, §3.3, ADR-001), catálogos y festivos
(SPEC 07, §3.6), y productos de crédito y topes de tasa (SPEC 08, §3.5).

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
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.auditoria.actions import AuditAction
from apps.auditoria.services import diff, record, snapshot
from apps.parametros.catalogs import RATE_CAP_USURY, Catalog
from apps.parametros.holidays import colombian_holidays
from apps.parametros.models import (
    SINGLETON_PK,
    CatalogItem,
    CreditProduct,
    GlobalSettings,
    Holiday,
    HolidayOrigin,
    ProductRateVersion,
    RateCapType,
    RateCapValue,
    RateUnit,
    RoundingMode,
    ValidityVersion,
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


# Productos de crédito y topes de tasa: lectura (SPEC 08, §3.5)
#
# No piden permisos: el simulador y la solicitud los usan con cualquier rol.
# Fuera de `apps.parametros`, nadie lee estos modelos con `objects`.


@dataclass(frozen=True)
class ApplicableCap:
    """Un tope que aplica a un producto y su valor vigente en una fecha."""

    cap_type: RateCapType
    value: RateCapValue | None  # None: no hay valor vigente en esa fecha


def _on(day: date | None) -> date:
    """La fecha de la consulta: `day`, o hoy en la zona horaria del negocio."""
    return day if day is not None else timezone.localdate()


def _live_versions[V: ValidityVersion](queryset: QuerySet[V], day: date) -> QuerySet[V]:
    """Las versiones no anuladas que empezaron a regir hasta `day`."""
    return queryset.filter(voided_at__isnull=True, valid_from__lte=day)


def _current_version[V: ValidityVersion](queryset: QuerySet[V], day: date) -> V | None:
    """La versión vigente en `day`: la no anulada con el mayor `valid_from`."""
    return _live_versions(queryset, day).order_by("-valid_from").first()


def get_offerable_products(on: date | None = None) -> QuerySet[CreditProduct]:
    """
    Los productos activos con una versión de tasa vigente en `on` (hoy si es
    `None`), por nombre. Es la lista que ofrecen el simulador y la solicitud.
    """
    live = _live_versions(
        ProductRateVersion.objects.filter(product=OuterRef("pk")), _on(on)
    )
    return (
        CreditProduct.objects.filter(is_active=True)
        .filter(Exists(live))
        .select_related("additional_rate_cap")
        .order_by("name")
    )


def get_product(pk: int) -> CreditProduct:
    """El producto con ese `pk`, activo o no. Lanza `CreditProduct.DoesNotExist`."""
    return CreditProduct.objects.select_related("additional_rate_cap").get(pk=pk)


def get_rate_version(
    product: CreditProduct, on: date | None = None
) -> ProductRateVersion | None:
    """La versión de tasa del producto vigente en `on` (hoy si es `None`), o `None`."""
    return _current_version(ProductRateVersion.objects.filter(product=product), _on(on))


def get_rate_cap_value(
    cap_type: RateCapType, on: date | None = None
) -> RateCapValue | None:
    """El valor del tope vigente en `on` (hoy si es `None`), o `None`."""
    return _current_version(RateCapValue.objects.filter(cap_type=cap_type), _on(on))


def get_applicable_caps(
    product: CreditProduct, on: date | None = None
) -> list[ApplicableCap]:
    """
    Los topes que aplican al producto en `on` (hoy si es `None`).

    Siempre la usura primero y, si el producto tiene un tope adicional, ese
    después, cada uno con su valor vigente o con `value=None`. Gana el menor
    valor; la SPEC 16 no aprueba si alguno no tiene valor vigente.
    """
    day = _on(on)
    caps = [get_item_by_code(RateCapType, RATE_CAP_USURY)]
    if product.additional_rate_cap_id is not None:
        caps.append(product.additional_rate_cap)
    return [ApplicableCap(cap, get_rate_cap_value(cap, day)) for cap in caps]


def get_product_rounding_rule(product: CreditProduct) -> RoundingRule:
    """El redondeo propio del producto, o el global si no tiene."""
    if product.rounding_multiple is None or not product.rounding_mode:
        return get_rounding_rule()
    return RoundingRule(
        multiple=Decimal(product.rounding_multiple),
        mode=RoundingMode(product.rounding_mode),
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


def _check_rate_cap_not_in_use(cap_type: RateCapType) -> None:
    """
    Un tipo de tope que es el tope adicional de un producto activo no se
    desactiva (SPEC 08, §3.4). Los productos inactivos no lo impiden.
    """
    product = cap_type.products.filter(is_active=True).order_by("name").first()
    if product is not None:
        raise CatalogRuleError(
            _(
                "Lo usa el producto %(product)s. Quítalo del producto antes de "
                "desactivarlo."
            )
            % {"product": product.name}
        )


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
        if isinstance(locked, RateCapType):
            _check_rate_cap_not_in_use(locked)
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


# Productos de crédito y topes de tasa: edición (SPEC 08, §3.5)

# Campos auditables del producto: los de la §3.2 menos las fechas técnicas.
PRODUCT_AUDIT_FIELDS = (
    "name",
    "description",
    "is_active",
    "interest_method",
    "allowed_periodicities",
    "default_periodicity",
    "min_amount",
    "max_amount",
    "min_installments",
    "default_installments",
    "max_installments",
    "default_grace_periods",
    "max_grace_periods",
    "late_fee_daily_rate",
    "late_fee_cap_percent",
    "late_tolerance_days",
    "write_off_min_days_past_due",
    "initial_charge_type",
    "initial_charge_value",
    "max_active_credits_per_client",
    "rounding_multiple",
    "rounding_mode",
    "additional_rate_cap",
)
# Lo que se puede editar: todo menos el estado (tiene sus servicios) y el
# método, que no cambia después de crear el producto.
PRODUCT_EDIT_FIELDS = tuple(
    name
    for name in PRODUCT_AUDIT_FIELDS
    if name not in ("is_active", "interest_method")
)
PRODUCT_CREATE_FIELDS = ("interest_method", *PRODUCT_EDIT_FIELDS)
# Con tasa por periodo, la periodicidad tampoco cambia (§3.2).
PERIODICITY_FIELDS = ("allowed_periodicities", "default_periodicity")

RATE_VERSION_AUDIT_FIELDS = ("min_rate", "default_rate", "max_rate", "valid_from")
RATE_CAP_VALUE_AUDIT_FIELDS = ("annual_effective_rate", "valid_from", "reference")
VOID_AUDIT_FIELDS = ("voided_at", "voided_by")


class ProductRuleError(ValidationError):
    """Una regla de los productos, las tasas o los topes impide la acción."""


def _normalize_decimals(instance: models.Model) -> None:
    """
    Deja cada `Decimal` con los decimales de su campo.

    Así `10` y `10.0000` son el mismo valor en la auditoría y una edición sin
    cambios no registra nada. Va después de `full_clean()`, que ya convirtió los
    textos y validó los dígitos.
    """
    for field in instance._meta.concrete_fields:
        if isinstance(field, models.DecimalField):
            value = getattr(instance, field.attname)
            if isinstance(value, Decimal):
                setattr(
                    instance,
                    field.attname,
                    value.quantize(Decimal(1).scaleb(-field.decimal_places)),
                )


def _assign(
    instance: models.Model, data: Mapping[str, Any], fields: Iterable[str]
) -> None:
    """Asigna solo los `fields` que vienen en `data`; el resto se ignora."""
    for name in fields:
        if name in data:
            setattr(instance, name, data[name])


def create_product(
    actor: User, data: Mapping[str, Any], rate: Mapping[str, Any]
) -> CreditProduct:
    """
    Crea el producto y su primera versión de tasa en la misma transacción.

    `data` trae los campos del producto (el estado se ignora: nace activo) y
    `rate`, `min_rate`, `default_rate`, `max_rate` y `valid_from`. Si el
    producto o la versión no son válidos, lanza `ValidationError` y no se crea
    ninguno de los dos. Audita `productos.created` y `productos.rate_scheduled`.
    """
    _require(actor, CreditProduct, "add")
    product = CreditProduct(updated_by=actor)
    _assign(product, data, PRODUCT_CREATE_FIELDS)
    with transaction.atomic():
        product.full_clean()
        _normalize_decimals(product)
        product.save()
        record(
            AuditAction.PRODUCT_CREATED,
            actor=actor,
            target=product,
            changes=diff({}, snapshot(product, PRODUCT_AUDIT_FIELDS)),
        )
        version = ProductRateVersion(product=product)
        _assign(version, rate, RATE_VERSION_AUDIT_FIELDS)
        _schedule_version(
            actor,
            version,
            ProductRateVersion.objects.filter(product=product),
            RATE_VERSION_AUDIT_FIELDS,
            AuditAction.PRODUCT_RATE_SCHEDULED,
        )
    return product


def update_product(
    actor: User, product: CreditProduct, data: Mapping[str, Any]
) -> CreditProduct:
    """
    Edita las condiciones del producto. Sin cambios no guarda ni registra.

    Ignora `interest_method` y `is_active` y, con tasa por periodo, también la
    periodicidad. Lanza `ValidationError` con los errores por campo.
    """
    _require(actor, CreditProduct, "change")
    with transaction.atomic():
        locked = CreditProduct.objects.select_for_update().get(pk=product.pk)
        before = snapshot(locked, PRODUCT_AUDIT_FIELDS)
        fields = PRODUCT_EDIT_FIELDS
        if locked.rate_unit == RateUnit.PER_PERIOD:
            fields = tuple(name for name in fields if name not in PERIODICITY_FIELDS)
        _assign(locked, data, fields)
        locked.full_clean()
        _normalize_decimals(locked)
        changes = diff(before, snapshot(locked, PRODUCT_AUDIT_FIELDS))
        if not changes:
            return locked
        locked.updated_by = actor
        locked.save()
        record(
            AuditAction.PRODUCT_UPDATED,
            actor=actor,
            target=locked,
            changes=changes,
        )
    return locked


def deactivate_product(actor: User, product: CreditProduct) -> CreditProduct:
    """
    Desactiva el producto: deja de ofrecerse en solicitudes nuevas. Los
    créditos que ya lo usan no cambian. Lanza `ProductRuleError` si ya está
    inactivo.
    """
    return _set_product_active(actor, product, False)


def reactivate_product(actor: User, product: CreditProduct) -> CreditProduct:
    """Reactiva el producto. Lanza `ProductRuleError` si ya está activo."""
    return _set_product_active(actor, product, True)


def _set_product_active(
    actor: User, product: CreditProduct, active: bool
) -> CreditProduct:
    _require(actor, CreditProduct, "change")
    with transaction.atomic():
        locked = CreditProduct.objects.select_for_update().get(pk=product.pk)
        if locked.is_active == active:
            raise ProductRuleError(
                _("El producto ya está activo.")
                if active
                else _("El producto ya está inactivo.")
            )
        before = snapshot(locked, PRODUCT_AUDIT_FIELDS)
        locked.is_active = active
        locked.updated_by = actor
        locked.save()
        record(
            (
                AuditAction.PRODUCT_REACTIVATED
                if active
                else AuditAction.PRODUCT_DEACTIVATED
            ),
            actor=actor,
            target=locked,
            changes=diff(before, snapshot(locked, PRODUCT_AUDIT_FIELDS)),
        )
    return locked


def schedule_rate_version(
    actor: User, product: CreditProduct, data: Mapping[str, Any]
) -> ProductRateVersion:
    """
    Programa una versión de tasa que rige desde `valid_from` (hoy o después,
    y después de la última no anulada). Cierra la versión anterior.

    Lanza `ValidationError` con los errores por campo.
    """
    _require(actor, ProductRateVersion, "add")
    with transaction.atomic():
        locked = CreditProduct.objects.select_for_update().get(pk=product.pk)
        version = ProductRateVersion(product=locked)
        _assign(version, data, RATE_VERSION_AUDIT_FIELDS)
        return _schedule_version(
            actor,
            version,
            ProductRateVersion.objects.filter(product=locked),
            RATE_VERSION_AUDIT_FIELDS,
            AuditAction.PRODUCT_RATE_SCHEDULED,
        )


def void_rate_version(actor: User, version: ProductRateVersion) -> ProductRateVersion:
    """
    Anula una versión programada: la última, y solo si todavía no rige.
    Reabre la anterior. Lanza `ProductRuleError` si no se puede.
    """
    _require(actor, ProductRateVersion, "change")
    with transaction.atomic():
        CreditProduct.objects.select_for_update().get(pk=version.product_id)
        return _void_version(
            actor,
            ProductRateVersion.objects.get(pk=version.pk),
            ProductRateVersion.objects.filter(product_id=version.product_id),
            AuditAction.PRODUCT_RATE_VOIDED,
        )


def schedule_rate_cap_value(
    actor: User, cap_type: RateCapType, data: Mapping[str, Any]
) -> RateCapValue:
    """
    Programa un valor del tope, en % EA, que rige desde `valid_from`, con su
    `reference`. Sigue las mismas reglas que las versiones de tasa.
    """
    _require(actor, RateCapValue, "add")
    with transaction.atomic():
        locked = RateCapType.objects.select_for_update().get(pk=cap_type.pk)
        value = RateCapValue(cap_type=locked)
        _assign(value, data, RATE_CAP_VALUE_AUDIT_FIELDS)
        return _schedule_version(
            actor,
            value,
            RateCapValue.objects.filter(cap_type=locked),
            RATE_CAP_VALUE_AUDIT_FIELDS,
            AuditAction.RATE_CAP_VALUE_SCHEDULED,
        )


def void_rate_cap_value(actor: User, value: RateCapValue) -> RateCapValue:
    """Anula un valor programado del tope, con las reglas de las versiones."""
    _require(actor, RateCapValue, "change")
    with transaction.atomic():
        RateCapType.objects.select_for_update().get(pk=value.cap_type_id)
        return _void_version(
            actor,
            RateCapValue.objects.get(pk=value.pk),
            RateCapValue.objects.filter(cap_type_id=value.cap_type_id),
            AuditAction.RATE_CAP_VALUE_VOIDED,
        )


def _latest_version[V: ValidityVersion](siblings: QuerySet[V]) -> V | None:
    """La última versión no anulada del historial, rija o no."""
    return siblings.filter(voided_at__isnull=True).order_by("-valid_from").first()


def _schedule_version[V: ValidityVersion](
    actor: User,
    version: V,
    siblings: QuerySet[V],
    fields: tuple[str, ...],
    action: AuditAction,
) -> V:
    """
    Valida, cierra la anterior, guarda y audita una versión nueva (§3.3).

    Va dentro de la transacción de quien llama, con el producto o el tipo de
    tope ya bloqueado, para que dos versiones no se crucen.
    """
    from apps.parametros.formatting import format_date

    errors: dict[str, Any] = {}
    latest = _latest_version(siblings)
    valid_from = version.valid_from
    if isinstance(valid_from, date):
        if valid_from < timezone.localdate():
            errors["valid_from"] = _(
                "La vigencia no puede empezar en una fecha pasada."
            )
        elif latest is not None and valid_from <= latest.valid_from:
            errors["valid_from"] = _(
                "La vigencia tiene que empezar después del %(date)s, cuando empieza "
                "la última versión. Para corregir una versión programada, anúlala "
                "primero."
            ) % {"date": format_date(latest.valid_from)}

    version.created_by = actor
    try:
        version.full_clean()
    except ValidationError as error:
        for field, messages in error.message_dict.items():
            errors.setdefault(field, messages)
    if errors:
        raise ValidationError(errors)
    _normalize_decimals(version)

    extra: dict[str, Any] = {}
    if latest is not None:
        latest.valid_to = version.valid_from - timedelta(days=1)
        latest.save(update_fields=["valid_to"])
        extra = {"closed_pk": latest.pk, "closed_valid_to": latest.valid_to}
    version.save()
    record(
        action,
        actor=actor,
        target=version,
        changes=diff({}, snapshot(version, fields)),
        extra=extra,
    )
    return version


def _void_version[V: ValidityVersion](
    actor: User, version: V, siblings: QuerySet[V], action: AuditAction
) -> V:
    """
    Anula la versión, reabre la anterior y audita (§3.3). Va dentro de la
    transacción de quien llama, con el dueño del historial bloqueado.
    """
    if version.voided_at is not None:
        raise ProductRuleError(_("Esa versión ya está anulada."))
    if version.valid_from <= timezone.localdate():
        raise ProductRuleError(
            _(
                "Esa versión ya rige o ya rigió, y un crédito pudo haberla usado: "
                "no se puede anular. Programa una nueva."
            )
        )
    latest = _latest_version(siblings)
    if latest is None or latest.pk != version.pk:
        raise ProductRuleError(_("Solo se puede anular la última versión programada."))

    before = snapshot(version, VOID_AUDIT_FIELDS)
    version.voided_at = timezone.now()
    version.voided_by = actor
    version.save(update_fields=["voided_at", "voided_by"])

    extra: dict[str, Any] = {}
    previous = _latest_version(siblings.exclude(pk=version.pk))
    if previous is not None:
        previous.valid_to = None
        previous.save(update_fields=["valid_to"])
        extra = {"reopened_pk": previous.pk}
    record(
        action,
        actor=actor,
        target=version,
        changes=diff(before, snapshot(version, VOID_AUDIT_FIELDS)),
        extra=extra,
    )
    return version
