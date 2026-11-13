"""
Parámetros globales (SPEC 06), catálogos y festivos (SPEC 07).

Los parámetros globales son un registro único (`pk=1`) con un campo tipado por
parámetro (ADR-001). Solo `apps.parametros.services` lee y escribe estos
modelos: el resto del sistema pasa por ese servicio, para que el día que haya
varios negocios solo cambie el servicio.
"""

from datetime import time
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
from django.db.models import Q
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
