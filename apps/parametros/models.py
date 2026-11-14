"""
Parámetros globales (SPEC 06), catálogos y festivos (SPEC 07), y productos de
crédito y tasas (SPEC 08).

Los parámetros globales son un registro único (`pk=1`) con un campo tipado por
parámetro (ADR-001). Solo `apps.parametros.services` lee y escribe estos
modelos: el resto del sistema pasa por ese servicio, para que el día que haya
varios negocios solo cambie el servicio.
"""

from datetime import time
from decimal import Decimal
from typing import Any, NoReturn, Self

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.db.models import F, Func, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

SINGLETON_PK = 1


class RoundingMode(models.TextChoices):
    HALF_UP = "half_up", _("Al más cercano")
    UP = "up", _("Siempre hacia arriba")
    DOWN = "down", _("Siempre hacia abajo")


class ShiftRule(models.TextChoices):
    CASCADE = "cascade", _("Correr también las cuotas siguientes")
    AFFECTED_ONLY = "affected_only", _("Correr solo la cuota afectada")


class DateFormat(models.TextChoices):
    DMY_SLASH = "d/m/Y", _("31/12/2026")
    DMY_DASH = "d-m-Y", _("31-12-2026")
    ISO = "Y-m-d", _("2026-12-31")
    LONG = r"j \d\e F \d\e Y", _("31 de diciembre de 2026")


class Weekday(models.IntegerChoices):
    """Días de la semana según ISO 8601 (`date.isoweekday()`): lunes = 1."""

    MONDAY = 1, _("Lunes")
    TUESDAY = 2, _("Martes")
    WEDNESDAY = 3, _("Miércoles")
    THURSDAY = 4, _("Jueves")
    FRIDAY = 5, _("Viernes")
    SATURDAY = 6, _("Sábado")
    SUNDAY = 7, _("Domingo")


ROUNDING_MULTIPLES = [1, 10, 50, 100, 500, 1000]
ROUNDING_MULTIPLE_CHOICES = [
    (value, f"{value:,}".replace(",", ".")) for value in ROUNDING_MULTIPLES
]

CURRENCY_DECIMAL_CHOICES = [(0, "0"), (2, "2")]

# Font Awesome Free 5.8.1, estilo solid. Lista cerrada para no aceptar clases
# inventadas en el HTML (SPEC 06, §6).
BRAND_ICON_CHOICES = [
    ("fas fa-hand-holding-usd", _("Mano con dinero")),
    ("fas fa-coins", _("Monedas")),
    ("fas fa-money-bill-wave", _("Billete")),
    ("fas fa-piggy-bank", _("Alcancía")),
    ("fas fa-wallet", _("Billetera")),
    ("fas fa-store", _("Tienda")),
    ("fas fa-handshake", _("Apretón de manos")),
    ("fas fa-university", _("Banco")),
]

# Rangos de seguridad y sesión: (mínimo, máximo).
RANGES: dict[str, tuple[int, int]] = {
    "max_failed_attempts": (3, 10),
    "lockout_minutes": (5, 120),
    "password_min_length": (8, 64),
    "password_reset_timeout_minutes": (15, 1440),
    "session_idle_timeout_minutes": (5, 240),
    "session_max_hours": (1, 24),
}


def _range_validators(field: str) -> list[Any]:
    low, high = RANGES[field]
    return [MinValueValidator(low), MaxValueValidator(high)]


def default_collection_weekdays() -> list[int]:
    return [
        Weekday.MONDAY,
        Weekday.TUESDAY,
        Weekday.WEDNESDAY,
        Weekday.THURSDAY,
        Weekday.FRIDAY,
        Weekday.SATURDAY,
    ]


def default_non_business_weekdays() -> list[int]:
    return [Weekday.SUNDAY]


def _range_constraints() -> list[models.CheckConstraint]:
    return [
        models.CheckConstraint(
            condition=Q(**{f"{field}__gte": low, f"{field}__lte": high}),
            name=f"parametros_globalsettings_{field}_range",
        )
        for field, (low, high) in RANGES.items()
    ]


class GlobalSettings(models.Model):
    """La configuración del negocio. Solo existe la fila `pk=1`."""

    # Negocio y formatos
    business_name = models.CharField(
        _("nombre del negocio"),
        max_length=100,
        default="Gestión de préstamos",
        help_text=_("Aparece en el título, el panel lateral y el pie de página."),
    )
    brand_icon = models.CharField(
        _("icono de la marca"),
        max_length=40,
        choices=BRAND_ICON_CHOICES,
        default="fas fa-hand-holding-usd",
    )
    currency_code = models.CharField(
        _("código de la moneda"),
        max_length=3,
        default="COP",
        help_text=_("Código de tres letras, por ejemplo COP."),
    )
    currency_symbol = models.CharField(
        _("símbolo de la moneda"), max_length=5, default="$"
    )
    currency_decimals = models.PositiveSmallIntegerField(
        _("decimales de la moneda"),
        choices=CURRENCY_DECIMAL_CHOICES,
        default=0,
        help_text=_(
            "Decimales que se muestran en los valores. No cambia los cálculos."
        ),
    )
    date_format = models.CharField(
        _("formato de fecha"),
        max_length=20,
        choices=DateFormat.choices,
        default=DateFormat.DMY_SLASH,
    )

    # Cobro y días no hábiles
    collection_weekdays = ArrayField(
        models.PositiveSmallIntegerField(choices=Weekday.choices),
        verbose_name=_("días de cobro"),
        default=default_collection_weekdays,
    )
    collection_start_time = models.TimeField(
        _("inicio del horario de cobro"), default=time(6, 0)
    )
    collection_end_time = models.TimeField(
        _("fin del horario de cobro"), default=time(20, 0)
    )
    non_business_weekdays = ArrayField(
        models.PositiveSmallIntegerField(choices=Weekday.choices),
        verbose_name=_("días de la semana no hábiles"),
        default=default_non_business_weekdays,
        blank=True,
        help_text=_("Los festivos se administran aparte."),
    )
    holiday_shift_rule = models.CharField(
        _("regla de corrimiento"),
        max_length=20,
        choices=ShiftRule.choices,
        default=ShiftRule.CASCADE,
        help_text=_("Qué pasa cuando una cuota cae en un día no hábil."),
    )

    # Redondeo
    rounding_multiple = models.PositiveIntegerField(
        _("múltiplo de redondeo"),
        choices=ROUNDING_MULTIPLE_CHOICES,
        default=50,
        help_text=_("Los valores de las cuotas se redondean a este múltiplo de pesos."),
    )
    rounding_mode = models.CharField(
        _("modo de redondeo"),
        max_length=10,
        choices=RoundingMode.choices,
        default=RoundingMode.HALF_UP,
    )

    # Seguridad y sesión
    max_failed_attempts = models.PositiveSmallIntegerField(
        _("intentos antes del bloqueo"),
        default=5,
        validators=_range_validators("max_failed_attempts"),
        help_text=_("Entre 3 y 10 intentos fallidos seguidos."),
    )
    lockout_minutes = models.PositiveSmallIntegerField(
        _("minutos de bloqueo"),
        default=15,
        validators=_range_validators("lockout_minutes"),
        help_text=_("Entre 5 y 120 minutos."),
    )
    password_min_length = models.PositiveSmallIntegerField(
        _("longitud mínima de la contraseña"),
        default=8,
        validators=_range_validators("password_min_length"),
        help_text=_(
            "Entre 8 y 64 caracteres. Aplica al siguiente cambio de contraseña; "
            "las contraseñas actuales siguen sirviendo."
        ),
    )
    password_reset_timeout_minutes = models.PositiveSmallIntegerField(
        _("vigencia del enlace de recuperación (minutos)"),
        default=60,
        validators=_range_validators("password_reset_timeout_minutes"),
        help_text=_("Entre 15 y 1.440 minutos."),
    )
    session_idle_timeout_minutes = models.PositiveSmallIntegerField(
        _("minutos de inactividad"),
        default=30,
        validators=_range_validators("session_idle_timeout_minutes"),
        help_text=_("Entre 5 y 240 minutos sin actividad cierran la sesión."),
    )
    session_max_hours = models.PositiveSmallIntegerField(
        _("duración máxima de la sesión (horas)"),
        default=12,
        validators=_range_validators("session_max_hours"),
        help_text=_("Entre 1 y 24 horas, aunque haya actividad."),
    )

    # Trazabilidad mínima en la fila
    updated_at = models.DateTimeField(_("última edición"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("editado por"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("parámetros globales")
        verbose_name_plural = _("parámetros globales")
        default_permissions = ("view", "change")
        constraints = [
            models.CheckConstraint(
                condition=Q(pk=SINGLETON_PK),
                name="parametros_globalsettings_singleton",
            ),
            *_range_constraints(),
        ]

    def __str__(self) -> str:
        return str(_("Parámetros globales"))

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = SINGLETON_PK
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied(_("Los parámetros globales no se pueden borrar."))

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        self.business_name = (self.business_name or "").strip()
        if not self.business_name:
            errors["business_name"] = _("Escribe el nombre del negocio.")

        code = (self.currency_code or "").strip().upper()
        self.currency_code = code
        if len(code) != 3 or not code.isascii() or not code.isalpha():
            errors["currency_code"] = _(
                "Usa el código de tres letras, por ejemplo COP."
            )

        self.currency_symbol = (self.currency_symbol or "").strip()
        if not self.currency_symbol:
            errors["currency_symbol"] = _("Escribe el símbolo de la moneda.")

        if not self.collection_weekdays:
            errors["collection_weekdays"] = _("Elige al menos un día de cobro.")

        if (
            self.collection_start_time is not None
            and self.collection_end_time is not None
            and self.collection_start_time >= self.collection_end_time
        ):
            errors["collection_end_time"] = _(
                "La hora de inicio debe ser anterior a la de fin."
            )

        if set(self.non_business_weekdays or []) >= set(Weekday.values):
            errors["non_business_weekdays"] = _("Debe haber al menos un día hábil.")

        if (
            self.session_idle_timeout_minutes is not None
            and self.session_max_hours is not None
            and self.session_idle_timeout_minutes >= self.session_max_hours * 60
        ):
            errors["session_idle_timeout_minutes"] = _(
                "La inactividad debe ser menor que la duración máxima."
            )

        if errors:
            raise ValidationError(errors)


# Catálogos de texto (SPEC 07, §3.1)

CODE_VALIDATOR = RegexValidator(
    r"^[A-Z0-9_]+$",
    _("Usa letras mayúsculas sin tildes, números y guion bajo."),
)


class CatalogItemQuerySet(models.QuerySet):
    def active(self) -> Self:
        """Los ítems activos, en el orden del catálogo."""
        return self.filter(is_active=True)


class CatalogItem(models.Model):
    """
    Base de los seis catálogos de texto. Cada catálogo es su propia tabla.

    El código no cambia después de crearse; el nombre y el orden sí. Nunca se
    borra un ítem: se desactiva.
    """

    code = models.CharField(
        _("código"),
        max_length=30,
        validators=[CODE_VALIDATOR],
        help_text=_("Letras mayúsculas, números y guion bajo. No cambia después."),
    )
    name = models.CharField(_("nombre"), max_length=100)
    display_order = models.PositiveSmallIntegerField(
        _("orden"),
        default=0,
        help_text=_("Los ítems se muestran de menor a mayor."),
    )
    is_active = models.BooleanField(_("activo"), default=True)
    is_system = models.BooleanField(
        _("de sistema"),
        default=False,
        editable=False,
        help_text=_("El sistema lo usa por su código: no se desactiva."),
    )

    created_at = models.DateTimeField(_("creado"), auto_now_add=True)
    updated_at = models.DateTimeField(_("última edición"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("editado por"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    objects = CatalogItemQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ("display_order", "name")
        default_permissions = ("view", "add", "change")
        constraints = [
            models.UniqueConstraint(
                fields=["code"], name="%(app_label)s_%(class)s_unique_code"
            ),
            models.UniqueConstraint(
                Lower("name"),
                name="%(app_label)s_%(class)s_unique_name",
                violation_error_message=_("Ya existe un ítem con ese nombre."),
            ),
            models.CheckConstraint(
                condition=Q(is_system=False) | Q(is_active=True),
                name="%(app_label)s_%(class)s_system_active",
                violation_error_message=_("Un ítem de sistema siempre está activo."),
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied(
            _("Los ítems de los catálogos no se borran: se desactivan.")
        )

    def clean_fields(self, exclude: Any = None) -> None:
        # El código se normaliza antes de que lo vea `CODE_VALIDATOR`.
        self.code = (self.code or "").strip().upper()
        super().clean_fields(exclude=exclude)

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        self.name = (self.name or "").strip()
        if not self.name:
            errors["name"] = _("Escribe el nombre.")
        elif (
            type(self)
            .objects.filter(name__iexact=self.name)
            .exclude(pk=self.pk)
            .exists()
        ):
            errors["name"] = _("Ya existe un ítem con ese nombre.")

        if errors:
            raise ValidationError(errors)


class DocumentType(CatalogItem):
    class Meta(CatalogItem.Meta):
        verbose_name = _("tipo de documento")
        verbose_name_plural = _("tipos de documento")


class Occupation(CatalogItem):
    class Meta(CatalogItem.Meta):
        verbose_name = _("ocupación")
        verbose_name_plural = _("ocupaciones")


class CreditPurpose(CatalogItem):
    class Meta(CatalogItem.Meta):
        verbose_name = _("destino de crédito")
        verbose_name_plural = _("destinos de crédito")


class VoidReason(CatalogItem):
    class Meta(CatalogItem.Meta):
        verbose_name = _("motivo de anulación")
        verbose_name_plural = _("motivos de anulación")


class RejectionReason(CatalogItem):
    class Meta(CatalogItem.Meta):
        verbose_name = _("motivo de rechazo")
        verbose_name_plural = _("motivos de rechazo")


class ThirdPartyRelationType(CatalogItem):
    class Meta(CatalogItem.Meta):
        verbose_name = _("tipo de relación de terceros")
        verbose_name_plural = _("tipos de relación de terceros")


# Festivos (SPEC 07, §3.2)


class HolidayOrigin(models.TextChoices):
    OFFICIAL = "official", _("Oficial")
    CUSTOM = "custom", _("Propio")


class Holiday(models.Model):
    """
    Un día no hábil por fecha: un festivo oficial (calculado) o uno propio.

    Los oficiales solo los crean la migración y el comando `cargar_festivos`,
    y se identifican por `official_year` y `official_code`.
    """

    date = models.DateField(_("fecha"))
    name = models.CharField(_("nombre"), max_length=100)
    origin = models.CharField(
        _("origen"),
        max_length=10,
        choices=HolidayOrigin.choices,
        default=HolidayOrigin.CUSTOM,
        editable=False,
    )
    official_code = models.CharField(
        _("código oficial"), max_length=40, blank=True, default="", editable=False
    )
    official_year = models.PositiveSmallIntegerField(
        _("año oficial"), null=True, blank=True, editable=False
    )
    is_active = models.BooleanField(_("activo"), default=True)

    created_at = models.DateTimeField(_("creado"), auto_now_add=True)
    updated_at = models.DateTimeField(_("última edición"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("editado por"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("festivo")
        verbose_name_plural = _("festivos")
        ordering = ("date",)
        default_permissions = ("view", "add", "change")
        constraints = [
            # Un solo festivo activo por fecha.
            models.UniqueConstraint(
                fields=["date"],
                condition=Q(is_active=True),
                name="parametros_holiday_unique_active_date",
                violation_error_message=_("Ya hay un festivo activo en esa fecha."),
            ),
            # Un festivo oficial se identifica por su año y su código.
            models.UniqueConstraint(
                fields=["official_year", "official_code"],
                condition=Q(origin=HolidayOrigin.OFFICIAL),
                name="parametros_holiday_unique_official",
            ),
            # Oficial ⇔ tiene código y año; propio ⇔ no tiene ninguno de los dos.
            models.CheckConstraint(
                condition=(
                    Q(origin=HolidayOrigin.OFFICIAL)
                    & ~Q(official_code="")
                    & Q(official_year__isnull=False)
                )
                | (
                    Q(origin=HolidayOrigin.CUSTOM)
                    & Q(official_code="")
                    & Q(official_year__isnull=True)
                ),
                name="parametros_holiday_origin_fields",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.date.isoformat()})"

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied(_("Los festivos no se borran: se desactivan."))

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        self.name = (self.name or "").strip()
        if not self.name:
            errors["name"] = _("Escribe el nombre.")

        if (
            self.is_active
            and self.date is not None
            and Holiday.objects.filter(date=self.date, is_active=True)
            .exclude(pk=self.pk)
            .exists()
        ):
            # Importación tardía: `formatting` lee los parámetros globales.
            from apps.parametros.formatting import format_date

            errors["date"] = _("Ya hay un festivo activo el %(date)s.") % {
                "date": format_date(self.date)
            }

        if errors:
            raise ValidationError(errors)


# Productos de crédito y tasas (SPEC 08, §3.1 a §3.4)


class InterestMethod(models.TextChoices):
    """Los seis métodos de interés (D12). Los valores son el contrato con el motor."""

    FLAT_PER_CREDIT = "flat_per_credit", _("Plano fijo por crédito")
    FLAT_MONTHLY_PRORATED = "flat_monthly_prorated", _("Plano mensual prorrateado")
    FLAT_PER_INSTALLMENT = "flat_per_installment", _("Plano por cuota")
    FRENCH = "french", _("Cuota fija (francés)")
    GERMAN = "german", _("Capital fijo (alemán)")
    DECLINING_BALANCE = "declining_balance", _("Interés sobre saldo")


class RateUnit(models.TextChoices):
    PER_CREDIT = "per_credit", _("% por crédito")
    MONTHLY = "monthly", _("% mensual")
    PER_PERIOD = "per_period", _("% por periodo")


# El método fija la unidad en que se guarda la tasa (§3.1).
METHOD_RATE_UNIT: dict[InterestMethod, RateUnit] = {
    InterestMethod.FLAT_PER_CREDIT: RateUnit.PER_CREDIT,
    InterestMethod.FLAT_MONTHLY_PRORATED: RateUnit.MONTHLY,
    InterestMethod.FLAT_PER_INSTALLMENT: RateUnit.PER_PERIOD,
    InterestMethod.FRENCH: RateUnit.PER_PERIOD,
    InterestMethod.GERMAN: RateUnit.PER_PERIOD,
    InterestMethod.DECLINING_BALANCE: RateUnit.PER_PERIOD,
}

PER_PERIOD_METHODS: tuple[str, ...] = tuple(
    method.value
    for method, unit in METHOD_RATE_UNIT.items()
    if unit == RateUnit.PER_PERIOD
)


class Periodicity(models.TextChoices):
    """Las cuatro periodicidades (D4). Los valores son el contrato con el motor."""

    DAILY = "daily", _("Diaria")
    WEEKLY = "weekly", _("Semanal")
    BIWEEKLY = "biweekly", _("Quincenal")
    MONTHLY = "monthly", _("Mensual")


class InitialChargeType(models.TextChoices):
    NONE = "none", _("Sin gasto inicial")
    FIXED = "fixed", _("Valor fijo")
    PERCENT = "percent", _("Porcentaje del monto")


MONEY = {"max_digits": 14, "decimal_places": 2}
PERCENT = {"max_digits": 7, "decimal_places": 4}  # hasta 100.0000

MAX_INSTALLMENTS = 999
MAX_LATE_TOLERANCE_DAYS = 90
MAX_PERCENT = Decimal("100")
MAX_RATE_CAP = Decimal("9999.9999")


def _percent_validators() -> list[Any]:
    return [MinValueValidator(Decimal("0")), MaxValueValidator(MAX_PERCENT)]


def _number(value: Any) -> Decimal | int | None:
    """
    El valor si ya es un número, o `None`.

    Si un campo falla en `clean_fields()`, Django lo deja con el valor original
    (por ejemplo, un texto). Así `clean()` solo compara números y deja ese
    error en su campo.
    """
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        return None
    return value


class RateCapType(CatalogItem):
    """Un tipo de tope de tasa (§3.4). "Usura" es el ítem de sistema `USURA`."""

    class Meta(CatalogItem.Meta):
        verbose_name = _("tipo de tope de tasa")
        verbose_name_plural = _("tipos de tope de tasa")


def _product_constraints() -> list[models.BaseConstraint]:
    """Las reglas de la §3.2 que caben en SQL (`parametros_creditproduct_<regla>`)."""

    def check(name: str, condition: Q) -> models.CheckConstraint:
        return models.CheckConstraint(
            condition=condition, name=f"parametros_creditproduct_{name}"
        )

    return [
        models.UniqueConstraint(
            Lower("name"),
            name="parametros_creditproduct_unique_name",
            violation_error_message=_("Ya existe un producto con ese nombre."),
        ),
        check(
            "amount_range",
            Q(min_amount__gt=0) & Q(min_amount__lte=F("max_amount")),
        ),
        check(
            "installments_range",
            Q(min_installments__gte=1)
            & Q(min_installments__lte=F("default_installments"))
            & Q(default_installments__lte=F("max_installments"))
            & Q(max_installments__lte=MAX_INSTALLMENTS),
        ),
        # Que no se repitan valores no cabe en un CHECK: lo valida `clean()`.
        check(
            "periodicities_valid",
            Q(allowed_periodicities__len__gte=1)
            & Q(allowed_periodicities__contained_by=list(Periodicity.values)),
        ),
        check(
            "default_periodicity_allowed",
            Q(
                allowed_periodicities__contains=Func(
                    F("default_periodicity"),
                    template="ARRAY[%(expressions)s]",
                    output_field=ArrayField(models.CharField(max_length=10)),
                )
            ),
        ),
        check(
            "per_period_single_periodicity",
            ~Q(interest_method__in=PER_PERIOD_METHODS)
            | Q(allowed_periodicities__len=1),
        ),
        check(
            "grace_range",
            Q(default_grace_periods__lte=F("max_grace_periods"))
            & Q(max_grace_periods__lt=F("min_installments")),
        ),
        check(
            "late_fee_range",
            Q(late_fee_daily_rate__gte=0)
            & Q(late_fee_daily_rate__lte=MAX_PERCENT)
            & Q(late_fee_cap_percent__gte=0)
            & Q(late_fee_cap_percent__lte=MAX_PERCENT),
        ),
        check(
            "late_tolerance_range",
            Q(late_tolerance_days__lte=MAX_LATE_TOLERANCE_DAYS),
        ),
        check("write_off_days_min", Q(write_off_min_days_past_due__gte=1)),
        check(
            "initial_charge_value",
            Q(initial_charge_type=InitialChargeType.NONE, initial_charge_value=0)
            | Q(
                initial_charge_type=InitialChargeType.FIXED,
                initial_charge_value__gt=0,
                initial_charge_value__lt=F("min_amount"),
            )
            | Q(
                initial_charge_type=InitialChargeType.PERCENT,
                initial_charge_value__gt=0,
                initial_charge_value__lt=MAX_PERCENT,
            ),
        ),
        check("max_active_credits_min", Q(max_active_credits_per_client__gte=1)),
        check(
            "rounding_pair",
            Q(rounding_multiple__isnull=True, rounding_mode__isnull=True)
            | Q(rounding_multiple__isnull=False, rounding_mode__isnull=False),
        ),
    ]


class CreditProduct(models.Model):
    """
    Un producto de crédito (§3.2): método, periodicidades y condiciones.

    Las tasas viven en su historial (`ProductRateVersion`). El método no cambia
    después de crear el producto y, con tasa por periodo, la periodicidad
    tampoco. Nunca se borra: se desactiva.
    """

    # Identificación
    name = models.CharField(_("nombre"), max_length=100)
    description = models.TextField(_("descripción"), blank=True, default="")
    is_active = models.BooleanField(
        _("activo"),
        default=True,
        editable=False,
        help_text=_("Un producto inactivo no se ofrece en solicitudes nuevas."),
    )

    # Método y periodicidad
    interest_method = models.CharField(
        _("método de interés"),
        max_length=30,
        choices=InterestMethod.choices,
        help_text=_(
            "Plano fijo: % por crédito. Plano mensual: % mensual. Los demás: % por "
            "periodo, con una sola periodicidad."
        ),
    )
    allowed_periodicities = ArrayField(
        models.CharField(max_length=10, choices=Periodicity.choices),
        verbose_name=_("periodicidades permitidas"),
    )
    default_periodicity = models.CharField(
        _("periodicidad por defecto"), max_length=10, choices=Periodicity.choices
    )

    # Monto y cuotas
    min_amount = models.DecimalField(_("monto mínimo"), **MONEY)
    max_amount = models.DecimalField(_("monto máximo"), **MONEY)
    min_installments = models.PositiveSmallIntegerField(
        _("cuotas mínimas"),
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INSTALLMENTS)],
    )
    default_installments = models.PositiveSmallIntegerField(
        _("cuotas por defecto"),
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INSTALLMENTS)],
    )
    max_installments = models.PositiveSmallIntegerField(
        _("cuotas máximas"),
        validators=[MinValueValidator(1), MaxValueValidator(MAX_INSTALLMENTS)],
        help_text=_("Hasta 999 cuotas."),
    )

    # Gracia: periodos sin cuota
    default_grace_periods = models.PositiveSmallIntegerField(
        _("periodos de gracia por defecto"),
        default=0,
        help_text=_("Periodos sin cuota al empezar el crédito."),
    )
    max_grace_periods = models.PositiveSmallIntegerField(
        _("periodos de gracia máximos"),
        default=0,
        help_text=_("Tiene que ser menor que las cuotas mínimas."),
    )

    # Mora y castigo
    late_fee_daily_rate = models.DecimalField(
        _("mora diaria (%)"),
        **PERCENT,
        validators=_percent_validators(),
        help_text=_("Porcentaje diario sobre el valor vencido."),
    )
    late_fee_cap_percent = models.DecimalField(
        _("tope de la mora (%)"),
        **PERCENT,
        validators=_percent_validators(),
        help_text=_("Porcentaje máximo del valor vencido de la cuota."),
    )
    late_tolerance_days = models.PositiveSmallIntegerField(
        _("días de tolerancia"),
        default=0,
        validators=[MaxValueValidator(MAX_LATE_TOLERANCE_DAYS)],
        help_text=_("Días después del vencimiento sin cobrar mora. Hasta 90."),
    )
    write_off_min_days_past_due = models.PositiveSmallIntegerField(
        _("días de mora para castigar"),
        validators=[MinValueValidator(1)],
        help_text=_("Días de mora a partir de los cuales se puede castigar."),
    )

    # Gasto inicial
    initial_charge_type = models.CharField(
        _("tipo de gasto inicial"),
        max_length=10,
        choices=InitialChargeType.choices,
        default=InitialChargeType.NONE,
    )
    initial_charge_value = models.DecimalField(
        _("valor del gasto inicial"),
        **MONEY,
        default=Decimal("0"),
        help_text=_(
            "Un valor en pesos o un porcentaje del monto, según el tipo. Se "
            "descuenta al desembolsar."
        ),
    )

    # Límite y redondeo
    max_active_credits_per_client = models.PositiveSmallIntegerField(
        _("créditos activos por cliente"),
        default=1,
        validators=[MinValueValidator(1)],
        help_text=_(
            "Máximo de créditos de este producto que un cliente tiene a la vez."
        ),
    )
    rounding_multiple = models.PositiveIntegerField(
        _("múltiplo de redondeo"),
        null=True,
        blank=True,
        choices=ROUNDING_MULTIPLE_CHOICES,
        help_text=_("Vacío: usa el redondeo global."),
    )
    # `null` y no "" a propósito (§3.2): sin redondeo propio, el múltiplo y el
    # modo son NULL, y `rounding_pair` lo comprueba en SQL.
    rounding_mode = models.CharField(  # noqa: DJ001
        _("modo de redondeo"),
        max_length=10,
        null=True,
        blank=True,
        choices=RoundingMode.choices,
    )

    # Tope adicional (la usura aplica siempre)
    additional_rate_cap = models.ForeignKey(
        RateCapType,
        verbose_name=_("tope adicional"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="products",
        help_text=_("La usura aplica siempre. Gana el tope más estricto."),
    )

    created_at = models.DateTimeField(_("creado"), auto_now_add=True)
    updated_at = models.DateTimeField(_("última edición"), auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("editado por"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("producto de crédito")
        verbose_name_plural = _("productos de crédito")
        ordering = ("name",)
        default_permissions = ("view", "add", "change")
        constraints = _product_constraints()

    def __str__(self) -> str:
        return self.name

    @property
    def rate_unit(self) -> RateUnit:
        """La unidad de la tasa, fijada por el método (§3.1)."""
        return METHOD_RATE_UNIT[InterestMethod(self.interest_method)]

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied(
            _("Los productos de crédito no se borran: se desactivan.")
        )

    def clean(self) -> None:
        errors: dict[str, Any] = {}

        def add(field: str, message: Any) -> None:
            # El primer error de cada campo es el que se muestra.
            errors.setdefault(field, message)

        self._clean_name(add)
        self._clean_amounts(add)
        self._clean_installments(add)
        self._clean_periodicities(add)
        self._clean_grace(add)
        self._clean_initial_charge(add)
        self._clean_rounding(add)
        self._clean_additional_cap(add)

        if errors:
            raise ValidationError(errors)

    def _clean_name(self, add: Any) -> None:
        self.name = (self.name or "").strip()
        if not self.name:
            add("name", _("Escribe el nombre del producto."))
        elif (
            CreditProduct.objects.filter(name__iexact=self.name)
            .exclude(pk=self.pk)
            .exists()
        ):
            add("name", _("Ya existe un producto con ese nombre."))

    def _clean_amounts(self, add: Any) -> None:
        if _number(self.min_amount) is not None and _number(self.min_amount) <= 0:
            add("min_amount", _("El monto mínimo debe ser mayor que cero."))
        if (
            _number(self.min_amount) is not None
            and _number(self.max_amount) is not None
            and _number(self.max_amount) < _number(self.min_amount)
        ):
            add("max_amount", _("El monto máximo no puede ser menor que el mínimo."))

    def _clean_installments(self, add: Any) -> None:
        low = _number(self.min_installments)
        default = _number(self.default_installments)
        high = _number(self.max_installments)
        if low is not None and default is not None and default < low:
            add(
                "default_installments",
                _("Las cuotas por defecto no pueden ser menos que las mínimas."),
            )
        if default is not None and high is not None and high < default:
            add(
                "max_installments",
                _("Las cuotas máximas no pueden ser menos que las de por defecto."),
            )
        elif low is not None and high is not None and high < low:
            add(
                "max_installments",
                _("Las cuotas máximas no pueden ser menos que las mínimas."),
            )

    def _clean_periodicities(self, add: Any) -> None:
        allowed = list(self.allowed_periodicities or [])
        if not allowed:
            add("allowed_periodicities", _("Elige al menos una periodicidad."))
            return
        if len(set(allowed)) != len(allowed):
            add("allowed_periodicities", _("No repitas periodicidades."))
        if self.default_periodicity and self.default_periodicity not in allowed:
            add(
                "default_periodicity",
                _("La periodicidad por defecto tiene que estar entre las permitidas."),
            )
        if self.interest_method in PER_PERIOD_METHODS and len(set(allowed)) != 1:
            add(
                "allowed_periodicities",
                _(
                    "Con el método %(method)s, la tasa es por periodo y el "
                    "producto admite una sola periodicidad."
                )
                % {"method": InterestMethod(self.interest_method).label},
            )

    def _clean_grace(self, add: Any) -> None:
        default = _number(self.default_grace_periods)
        high = _number(self.max_grace_periods)
        if default is not None and high is not None and default > high:
            add(
                "default_grace_periods",
                _("Los periodos de gracia por defecto no pueden superar el máximo."),
            )
        if (
            high is not None
            and _number(self.min_installments) is not None
            and high >= _number(self.min_installments)
        ):
            add(
                "max_grace_periods",
                _(
                    "Los periodos de gracia tienen que ser menos que las cuotas "
                    "mínimas."
                ),
            )

    def _clean_initial_charge(self, add: Any) -> None:
        value = _number(self.initial_charge_value)
        if value is None:
            return
        kind = self.initial_charge_type
        if kind == InitialChargeType.NONE and value != 0:
            add(
                "initial_charge_value",
                _("Sin gasto inicial, el valor tiene que ser cero."),
            )
        elif kind == InitialChargeType.FIXED and (
            value <= 0
            or (
                _number(self.min_amount) is not None
                and value >= _number(self.min_amount)
            )
        ):
            add(
                "initial_charge_value",
                _(
                    "El gasto fijo debe ser mayor que cero y menor que el monto "
                    "mínimo."
                ),
            )
        elif kind == InitialChargeType.PERCENT and not 0 < value < MAX_PERCENT:
            add(
                "initial_charge_value",
                _("El porcentaje debe ser mayor que 0 y menor que 100."),
            )

    def _clean_rounding(self, add: Any) -> None:
        if self.rounding_mode == "":
            self.rounding_mode = None
        if (self.rounding_multiple is None) != (self.rounding_mode is None):
            add(
                "rounding_mode",
                _(
                    "Elige el múltiplo y el modo, o deja los dos vacíos para usar "
                    "el redondeo global."
                ),
            )

    def _clean_additional_cap(self, add: Any) -> None:
        cap = self.additional_rate_cap
        if cap is None:
            return
        # Importación tardía: `catalogs` importa este módulo.
        from apps.parametros.catalogs import RATE_CAP_USURY

        if cap.code == RATE_CAP_USURY:
            add("additional_rate_cap", _("La usura ya aplica a todos los productos."))
            return
        # Un tope desactivado después de asignarlo no invalida al producto.
        previous = (
            CreditProduct.objects.filter(pk=self.pk)
            .values_list("additional_rate_cap_id", flat=True)
            .first()
            if self.pk
            else None
        )
        if not cap.is_active and cap.pk != previous:
            add("additional_rate_cap", _("Ese tope está inactivo."))


class ValidityVersion(models.Model):
    """
    Una versión con vigencia (§3.3): se agrega, nunca se edita.

    `valid_to` y la anulación los mantiene el servicio. La versión vigente en
    una fecha es la no anulada con el mayor `valid_from` hasta esa fecha.
    """

    valid_from = models.DateField(_("rige desde"))
    valid_to = models.DateField(_("rige hasta"), null=True, blank=True, editable=False)
    voided_at = models.DateTimeField(
        _("anulada el"), null=True, blank=True, editable=False
    )
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("anulada por"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )
    created_at = models.DateTimeField(_("creada"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("creada por"),
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )

    class Meta:
        abstract = True
        default_permissions = ("view", "add", "change")
        constraints = [
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=F("valid_from")),
                name="%(app_label)s_%(class)s_valid_to_after_from",
            ),
            models.CheckConstraint(
                condition=Q(voided_at__isnull=True, voided_by__isnull=True)
                | Q(voided_at__isnull=False, voided_by__isnull=False),
                name="%(app_label)s_%(class)s_voided_pair",
            ),
        ]

    @property
    def is_voided(self) -> bool:
        return self.voided_at is not None

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied(_("Las versiones no se borran: se anulan."))


class ProductRateVersion(ValidityVersion):
    """Las tasas de un producto en un periodo, en la unidad de su método."""

    product = models.ForeignKey(
        CreditProduct,
        verbose_name=_("producto"),
        on_delete=models.PROTECT,
        related_name="rate_versions",
    )
    min_rate = models.DecimalField(
        _("tasa mínima"), **PERCENT, validators=_percent_validators()
    )
    default_rate = models.DecimalField(
        _("tasa por defecto"), **PERCENT, validators=_percent_validators()
    )
    max_rate = models.DecimalField(
        _("tasa máxima"), **PERCENT, validators=_percent_validators()
    )

    class Meta(ValidityVersion.Meta):
        verbose_name = _("versión de tasa")
        verbose_name_plural = _("versiones de tasa")
        ordering = ("product", "valid_from")
        constraints = [
            *ValidityVersion.Meta.constraints,
            models.UniqueConstraint(
                fields=["product", "valid_from"],
                condition=Q(voided_at__isnull=True),
                name="parametros_productrateversion_unique_from",
                violation_error_message=_("Ya hay una tasa que rige desde esa fecha."),
            ),
            models.CheckConstraint(
                condition=Q(min_rate__gte=0)
                & Q(min_rate__lte=F("default_rate"))
                & Q(default_rate__lte=F("max_rate"))
                & Q(max_rate__lte=MAX_PERCENT),
                name="parametros_productrateversion_rate_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} ({self.valid_from.isoformat()})"

    def clean(self) -> None:
        errors: dict[str, Any] = {}
        low, default, high = (
            _number(self.min_rate),
            _number(self.default_rate),
            _number(self.max_rate),
        )
        if low is not None and default is not None and default < low:
            errors["default_rate"] = _(
                "La tasa por defecto no puede ser menor que la mínima."
            )
        if default is not None and high is not None and high < default:
            errors["max_rate"] = _(
                "La tasa máxima no puede ser menor que la de por defecto."
            )
        if errors:
            raise ValidationError(errors)


class RateCapValue(ValidityVersion):
    """El valor de un tope de tasa en un periodo, en % efectivo anual."""

    cap_type = models.ForeignKey(
        RateCapType,
        verbose_name=_("tipo de tope"),
        on_delete=models.PROTECT,
        related_name="values",
    )
    annual_effective_rate = models.DecimalField(
        _("valor (% EA)"),
        max_digits=9,
        decimal_places=4,
        validators=[MaxValueValidator(MAX_RATE_CAP)],
    )
    reference = models.CharField(
        _("referencia"),
        max_length=150,
        blank=True,
        default="",
        help_text=_(
            "Por ejemplo, Resolución 1234 de 2026 de la Superintendencia Financiera."
        ),
    )

    class Meta(ValidityVersion.Meta):
        verbose_name = _("valor de tope de tasa")
        verbose_name_plural = _("valores de tope de tasa")
        ordering = ("cap_type", "valid_from")
        constraints = [
            *ValidityVersion.Meta.constraints,
            models.UniqueConstraint(
                fields=["cap_type", "valid_from"],
                condition=Q(voided_at__isnull=True),
                name="parametros_ratecapvalue_unique_from",
                violation_error_message=_("Ya hay un valor que rige desde esa fecha."),
            ),
            models.CheckConstraint(
                condition=Q(annual_effective_rate__gt=0)
                & Q(annual_effective_rate__lte=MAX_RATE_CAP),
                name="parametros_ratecapvalue_rate_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cap_type} ({self.valid_from.isoformat()})"

    def clean(self) -> None:
        self.reference = (self.reference or "").strip()
        if (
            _number(self.annual_effective_rate) is not None
            and _number(self.annual_effective_rate) <= 0
        ):
            raise ValidationError(
                {
                    "annual_effective_rate": _(
                        "El valor del tope debe ser mayor que cero."
                    )
                }
            )
