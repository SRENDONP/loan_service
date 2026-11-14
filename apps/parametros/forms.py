"""
Formularios de los parámetros globales, uno por grupo (SPEC 06, §3.9), de los
catálogos (SPEC 07) y de los productos y los topes de tasa (SPEC 08).

Solo validan y dibujan los campos: la vista pasa `cleaned_data` al servicio de
edición del grupo y nunca llama a `form.save()`.
"""

from typing import Any

from django import forms
from django.db.models import Q
from django.utils.translation import gettext as gettext_now
from django.utils.translation import gettext_lazy as _

from apps.parametros.catalogs import RATE_CAP_USURY
from apps.parametros.models import (
    ROUNDING_MULTIPLE_CHOICES,
    CatalogItem,
    CreditProduct,
    GlobalSettings,
    Holiday,
    InterestMethod,
    Periodicity,
    ProductRateVersion,
    RateCapType,
    RateCapValue,
    RateUnit,
    RoundingMode,
    Weekday,
)
from apps.parametros.services import (
    BUSINESS_FIELDS,
    COLLECTION_FIELDS,
    ROUNDING_FIELDS,
    SECURITY_FIELDS,
    get_rounding_rule,
)


def weekday_field(*, label: str, required: bool, **kwargs) -> forms.Field:
    return forms.TypedMultipleChoiceField(
        label=label,
        choices=Weekday.choices,
        coerce=int,
        required=required,
        widget=forms.CheckboxSelectMultiple,
        **kwargs,
    )


def time_widget() -> forms.TimeInput:
    return forms.TimeInput(attrs={"type": "time"}, format="%H:%M")


class BusinessForm(forms.ModelForm):
    class Meta:
        model = GlobalSettings
        fields = BUSINESS_FIELDS


class CollectionForm(forms.ModelForm):
    collection_weekdays = weekday_field(
        label=_("Días de cobro"),
        required=True,
        error_messages={"required": _("Elige al menos un día de cobro.")},
    )
    non_business_weekdays = weekday_field(
        label=_("Días de la semana no hábiles"),
        required=False,
        help_text=_("Los festivos se administran aparte."),
    )

    class Meta:
        model = GlobalSettings
        fields = COLLECTION_FIELDS
        widgets = {
            "collection_start_time": time_widget(),
            "collection_end_time": time_widget(),
        }


class RoundingForm(forms.ModelForm):
    class Meta:
        model = GlobalSettings
        fields = ROUNDING_FIELDS


class SecurityForm(forms.ModelForm):
    class Meta:
        model = GlobalSettings
        fields = SECURITY_FIELDS


# Catálogos de texto (SPEC 07, §3.10)


class CatalogItemCreateForm(forms.ModelForm):
    """
    Crear un ítem. El código es opcional: vacío, el servicio lo genera del
    nombre. Como el campo no es obligatorio en el formulario, un código vacío no
    pasa por la validación del modelo.
    """

    class Meta:
        model = CatalogItem
        fields = ("code", "name", "display_order")
        help_texts = {
            "code": _(
                "Si lo dejas vacío, se genera del nombre. "
                "No se puede cambiar después."
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False


class CatalogItemUpdateForm(forms.ModelForm):
    """Editar un ítem: solo el nombre y el orden. El código no es un campo."""

    class Meta:
        model = CatalogItem
        fields = ("name", "display_order")


class HolidayForm(forms.ModelForm):
    """
    Crear o editar un festivo: solo la fecha y el nombre. El origen, el código
    y el año oficial no son campos; el servicio crea siempre festivos propios.
    """

    class Meta:
        model = Holiday
        fields = ("date", "name")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }


def catalog_item_form(
    model: type[CatalogItem], *, creating: bool
) -> type[forms.ModelForm]:
    """El formulario de crear o de editar, ligado al modelo del catálogo."""
    base = CatalogItemCreateForm if creating else CatalogItemUpdateForm
    return forms.modelform_factory(model, form=base, fields=base.Meta.fields)


# Productos de crédito y topes de tasa (SPEC 08, §3.9)

SUFFIX_FIELD_TEMPLATE = "forms/field_suffix.html"


def date_widget() -> forms.DateInput:
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def add_suffix(field: forms.Field, suffix: str) -> None:
    """Dibuja el campo con su unidad al lado (`input-group-append`)."""
    field.template_name = SUFFIX_FIELD_TEMPLATE
    field.suffix = suffix


class RateCapValueForm(forms.ModelForm):
    """Programar un valor de un tope: el valor en % EA, desde cuándo y la fuente."""

    class Meta:
        model = RateCapValue
        fields = ("annual_effective_rate", "valid_from", "reference")
        widgets = {"valid_from": date_widget()}
        help_texts = {
            "valid_from": _(
                "Hoy o una fecha futura, después de la última versión programada."
            ),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        add_suffix(self.fields["annual_effective_rate"], _("% EA"))


# Las tarjetas del formulario y del detalle del producto, en orden (§3.9).
PRODUCT_FORM_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (_("Identificación"), ("name", "description")),
    (
        _("Método y periodicidad"),
        ("interest_method", "allowed_periodicities", "default_periodicity"),
    ),
    (
        _("Monto y cuotas"),
        (
            "min_amount",
            "max_amount",
            "min_installments",
            "default_installments",
            "max_installments",
        ),
    ),
    (_("Gracia"), ("default_grace_periods", "max_grace_periods")),
    (
        _("Mora y castigo"),
        (
            "late_fee_daily_rate",
            "late_fee_cap_percent",
            "late_tolerance_days",
            "write_off_min_days_past_due",
        ),
    ),
    (_("Gasto inicial"), ("initial_charge_type", "initial_charge_value")),
    (
        _("Límite y redondeo"),
        ("max_active_credits_per_client", "rounding_multiple", "rounding_mode"),
    ),
    (_("Tope adicional"), ("additional_rate_cap",)),
)
PRODUCT_FORM_FIELDS = tuple(
    name for _title, names in PRODUCT_FORM_GROUPS for name in names
)


def global_rounding_label() -> str:
    """El texto de la opción vacía del redondeo: "Usar el redondeo global (…)"."""
    rule = get_rounding_rule()
    multiple = dict(ROUNDING_MULTIPLE_CHOICES)[int(rule.multiple)]
    return gettext_now("Usar el redondeo global (%(multiple)s, %(mode)s)") % {
        "multiple": multiple,
        "mode": str(rule.mode.label).lower(),
    }


class CreditProductForm(forms.ModelForm):
    """
    Crear o editar un producto (§3.9). La vista pasa `cleaned_data` al servicio.

    Al editar, el método no es un campo y, con tasa por periodo, la periodicidad
    tampoco: la plantilla los muestra como texto. El tope adicional ofrece
    "Ninguno" y los tipos activos que no son la usura; uno ya asignado que se
    desactivó se sigue mostrando.
    """

    allowed_periodicities = forms.MultipleChoiceField(
        label=_("Periodicidades permitidas"),
        choices=Periodicity.choices,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Con tasa por periodo, elige una sola."),
    )

    class Meta:
        model = CreditProduct
        fields = PRODUCT_FORM_FIELDS
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, creating: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not creating:
            del self.fields["interest_method"]
            if self.instance.rate_unit == RateUnit.PER_PERIOD:
                del self.fields["allowed_periodicities"]
                del self.fields["default_periodicity"]

        # Django 6.1 trae "- Select an option -" sin traducir como opción vacía.
        for name, choices in (
            ("interest_method", InterestMethod.choices),
            ("default_periodicity", Periodicity.choices),
        ):
            if name in self.fields:
                self.fields[name].choices = [("", _("Elige una opción")), *choices]

        self.fields["rounding_multiple"].choices = [
            ("", global_rounding_label()),
            *ROUNDING_MULTIPLE_CHOICES,
        ]
        self.fields["rounding_mode"].choices = [
            ("", _("Usar el redondeo global")),
            *RoundingMode.choices,
        ]

        caps = RateCapType.objects.filter(is_active=True).exclude(code=RATE_CAP_USURY)
        if self.instance.additional_rate_cap_id is not None:
            caps = RateCapType.objects.filter(
                Q(pk__in=caps) | Q(pk=self.instance.additional_rate_cap_id)
            )
        cap_field = self.fields["additional_rate_cap"]
        cap_field.queryset = caps.order_by("display_order", "name")
        cap_field.empty_label = _("Ninguno")

        add_suffix(self.fields["late_fee_daily_rate"], _("% diario"))
        add_suffix(self.fields["late_fee_cap_percent"], "%")

    def groups(self) -> list[tuple[str, list[forms.BoundField]]]:
        """Los campos de cada tarjeta que están en el formulario, en su orden."""
        return [
            (title, [self[name] for name in names if name in self.fields])
            for title, names in PRODUCT_FORM_GROUPS
        ]


class RateVersionForm(forms.ModelForm):
    """
    Las tasas de una versión y desde cuándo rige. Con `unit`, cada tasa lleva la
    unidad del producto como sufijo; al crear un producto la unidad todavía no
    se conoce y el sufijo es "%".
    """

    class Meta:
        model = ProductRateVersion
        fields = ("min_rate", "default_rate", "max_rate", "valid_from")
        widgets = {"valid_from": date_widget()}
        help_texts = {
            "valid_from": _(
                "Hoy o una fecha futura, después de la última versión programada."
            ),
        }

    def __init__(self, *args: Any, unit: str = "%", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for name in ("min_rate", "default_rate", "max_rate"):
            add_suffix(self.fields[name], unit)
