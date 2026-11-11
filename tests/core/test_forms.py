"""Pruebas del renderizador de formularios con Bootstrap 4 (SPEC 02, paso 8)."""

import re

from django import forms
from django.forms.renderers import get_default_renderer
from django.template import Context, Template

from apps.core.forms import BootstrapFormRenderer, ComponentsDemoForm

VALID_DATA = {
    "name": "Ana Gómez",
    "email": "ana@example.com",
    "request_type": "consulta",
    "notes": "",
    "accepts_terms": "on",
}


def render(form: forms.Form) -> str:
    """Renderiza como lo hace una plantilla: `{{ form }}`."""
    return Template("{{ form }}").render(Context({"form": form}))


def tag_with_id(html: str, element: str, element_id: str) -> str:
    match = re.search(rf'<{element}\b[^>]*\bid="{element_id}"[^>]*>', html)
    assert match, f'No hay <{element} id="{element_id}">'
    return match.group(0)


def classes_of(tag: str) -> list[str]:
    match = re.search(r'\bclass="([^"]*)"', tag)
    assert match, f"Sin atributo class: {tag}"
    return match.group(1).split()


def test_default_renderer_is_bootstrap():
    assert isinstance(get_default_renderer(), BootstrapFormRenderer)


def test_valid_form_uses_bootstrap_classes_without_errors():
    form = ComponentsDemoForm(data=VALID_DATA)
    assert form.is_valid()

    html = render(form)

    assert html.count('<div class="form-group">') == 5
    for field_id in ("id_name", "id_email"):
        assert classes_of(tag_with_id(html, "input", field_id)) == ["form-control"]
    assert classes_of(tag_with_id(html, "select", "id_request_type")) == [
        "form-control"
    ]
    assert classes_of(tag_with_id(html, "textarea", "id_notes")) == ["form-control"]
    assert classes_of(tag_with_id(html, "input", "id_accepts_terms")) == [
        "form-check-input"
    ]
    assert "is-invalid" not in html
    assert "invalid-feedback" not in html
    assert "alert-danger" not in html


def test_invalid_field_gets_is_invalid_and_feedback():
    form = ComponentsDemoForm(data={**VALID_DATA, "email": "no-es-correo"})
    assert not form.is_valid()

    html = render(form)

    email = tag_with_id(html, "input", "id_email")
    assert classes_of(email) == ["form-control", "is-invalid"]
    assert 'aria-describedby="id_email_error"' in email
    feedback = re.search(
        r'<div class="invalid-feedback" id="id_email_error">\s*(.*?)\s*</div>',
        html,
        re.S,
    )
    assert feedback
    assert feedback.group(1) == form.errors["email"][0]
    # Los demás campos siguen sin error.
    assert classes_of(tag_with_id(html, "input", "id_name")) == ["form-control"]


def test_labels_point_to_field_ids():
    html = render(ComponentsDemoForm(data={}))

    for field_id in (
        "id_name",
        "id_email",
        "id_request_type",
        "id_notes",
        "id_accepts_terms",
    ):
        assert f'<label for="{field_id}"' in html or (
            f'<label class="form-check-label" for="{field_id}"' in html
        )
        assert f'id="{field_id}"' in html


def test_invalid_checkbox_uses_form_check_markup():
    html = render(ComponentsDemoForm(data={**VALID_DATA, "accepts_terms": ""}))

    checkbox = tag_with_id(html, "input", "id_accepts_terms")
    assert classes_of(checkbox) == ["form-check-input", "is-invalid"]
    assert re.search(
        r'<div class="form-check">\s*<input[^>]*id="id_accepts_terms"[^>]*>\s*'
        r'<label class="form-check-label" for="id_accepts_terms">'
        r"Acepto los términos</label>\s*"
        r'<div class="invalid-feedback" id="id_accepts_terms_error">',
        html,
    )


def test_help_text_is_linked_to_field():
    html = render(ComponentsDemoForm())

    assert 'aria-describedby="id_name_helptext"' in tag_with_id(
        html, "input", "id_name"
    )
    assert re.search(
        r'<small class="form-text text-muted" id="id_name_helptext">'
        r"Nombre y apellido, como aparece en el documento.</small>",
        html,
    )


def test_non_field_errors_render_as_alert():
    form = ComponentsDemoForm(data={**VALID_DATA, "request_type": "otro"})
    assert not form.is_valid()

    html = render(form)

    assert re.search(
        r'<div class="alert alert-danger" role="alert">\s*'
        r"Si eliges «Otro», escribe una observación.\s*</div>",
        html,
    )


def test_widget_css_class_is_kept_after_bootstrap_class():
    class ExtraClassForm(forms.Form):
        amount = forms.CharField(widget=forms.TextInput(attrs={"class": "text-right"}))

    html = render(ExtraClassForm(data={}))

    classes = classes_of(tag_with_id(html, "input", "id_amount"))
    assert classes[0] == "form-control"
    assert set(classes) == {"form-control", "is-invalid", "text-right"}


def test_widgets_without_override_fall_back_to_django():
    class HiddenForm(forms.Form):
        token = forms.CharField(widget=forms.HiddenInput)

    html = render(HiddenForm(initial={"token": "abc"}))

    assert (
        html.strip() == '<input type="hidden" name="token" value="abc" id="id_token">'
    )
