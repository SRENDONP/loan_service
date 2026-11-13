"""
Formularios de los parámetros globales, uno por grupo (SPEC 06, §3.9).

Solo validan y dibujan los campos: la vista pasa `cleaned_data` al servicio de
edición del grupo y nunca llama a `form.save()`.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.parametros.models import CatalogItem, GlobalSettings, Holiday, Weekday
from apps.parametros.services import (
    BUSINESS_FIELDS,
    COLLECTION_FIELDS,
    ROUNDING_FIELDS,
    SECURITY_FIELDS,
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
