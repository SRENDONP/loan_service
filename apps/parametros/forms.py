"""
Formularios de los parámetros globales, uno por grupo (SPEC 06, §3.9).

Solo validan y dibujan los campos: la vista pasa `cleaned_data` al servicio de
edición del grupo y nunca llama a `form.save()`.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.parametros.models import GlobalSettings, Weekday
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
