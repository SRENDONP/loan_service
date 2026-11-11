"""Renderizador de formularios con Bootstrap 4 y formulario de ejemplo (SPEC 02).

`BootstrapFormRenderer` hace que `{{ form }}` salga con las clases de Bootstrap
4 que usa SB Admin 2 (`form-group`, `form-control`, `is-invalid`,
`invalid-feedback`), sin librerías externas ni mixins en los widgets.
"""

from django import forms
from django.forms.renderers import TemplatesSetting
from django.template import Template, TemplateDoesNotExist
from django.utils.translation import gettext_lazy as _

DJANGO_PREFIX = "django/forms/"
PROJECT_PREFIX = "forms/"


class BootstrapFormRenderer(TemplatesSetting):
    """Renderiza formularios con las plantillas de `templates/forms/`.

    El formulario y el campo usan `forms/form.html` y `forms/field.html`. Para
    los demás (etiqueta, widgets), si existe `forms/<ruta>` se usa en lugar de
    `django/forms/<ruta>`; si no, se usa la plantilla de Django.
    """

    form_template_name = "forms/form.html"
    field_template_name = "forms/field.html"

    def get_template(self, template_name: str) -> Template:
        if template_name.startswith(DJANGO_PREFIX):
            override = PROJECT_PREFIX + template_name.removeprefix(DJANGO_PREFIX)
            try:
                return super().get_template(override)
            except TemplateDoesNotExist:
                pass
        return super().get_template(template_name)


class ComponentsDemoForm(forms.Form):
    """Formulario de ejemplo para el catálogo de componentes y sus pruebas."""

    TYPE_OTHER = "otro"
    TYPE_CHOICES = [
        ("", _("Selecciona un tipo")),
        ("consulta", _("Consulta")),
        ("reclamo", _("Reclamo")),
        (TYPE_OTHER, _("Otro")),
    ]

    name = forms.CharField(
        label=_("Nombre"),
        max_length=100,
        help_text=_("Nombre y apellido, como aparece en el documento."),
    )
    email = forms.EmailField(label=_("Correo electrónico"))
    request_type = forms.ChoiceField(label=_("Tipo de solicitud"), choices=TYPE_CHOICES)
    notes = forms.CharField(
        label=_("Observaciones"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    accepts_terms = forms.BooleanField(label=_("Acepto los términos"))

    def clean(self) -> dict[str, object]:
        cleaned_data = super().clean()
        if cleaned_data.get("request_type") == self.TYPE_OTHER and not cleaned_data.get(
            "notes"
        ):
            raise forms.ValidationError(
                _("Si eliges «Otro», escribe una observación."),
                code="notes_required",
            )
        return cleaned_data
