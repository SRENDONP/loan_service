"""Formularios de autenticación (SPEC 03) y de gestión de usuarios (SPEC 04)."""

from typing import Any

from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import DocumentType, User
from apps.accounts.roles import Role
from apps.accounts.services import (
    DEACTIVATION_REASON_MAX_LENGTH,
    authenticate_with_lockout,
    clear_failed_attempts,
    mark_password_changed,
)

# Variante de estilo de los campos en las pantallas de autenticación de SB Admin
# 2 (`login.html`, `forgot-password.html`). La clase base `form-control` la pone
# el renderizador de formularios del proyecto.
AUTH_INPUT_CLASS = "form-control-user"


class AuthPageFormMixin:
    """
    Da a los campos el estilo de las pantallas de autenticación de SB Admin 2.

    Es el único lugar que agrega `form-control-user` y el placeholder (el texto
    de la etiqueta) a los widgets. La plantilla muestra la etiqueta solo para
    lectores de pantalla, como la referencia, que no tiene etiquetas visibles.
    """

    fields: dict[str, forms.Field]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            attrs = field.widget.attrs
            attrs["class"] = f"{attrs.get('class', '')} {AUTH_INPUT_CLASS}".strip()
            attrs.setdefault("placeholder", field.label)


class LoginForm(AuthPageFormMixin, AuthenticationForm):
    """
    Inicio de sesión con nombre de usuario o correo y bloqueo temporal.

    Todo fallo (contraseña incorrecta, usuario inexistente, inactivo o cuenta
    bloqueada) muestra el mismo mensaje, para no revelar qué usuarios existen.
    """

    username = forms.CharField(
        label=_("Usuario o correo"),
        max_length=254,
        widget=forms.TextInput(
            attrs={"autofocus": True, "autocomplete": "username"},
        ),
    )

    error_messages = {
        "invalid_login": _(
            "El usuario, el correo o la contraseña no son correctos. Después de "
            "varios intentos fallidos, la cuenta se bloquea unos minutos."
        ),
        "inactive": _(
            "El usuario, el correo o la contraseña no son correctos. Después de "
            "varios intentos fallidos, la cuenta se bloquea unos minutos."
        ),
    }

    def clean(self) -> dict[str, Any]:
        identifier = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if identifier is not None and password:
            self.user_cache = authenticate_with_lockout(
                self.request, identifier, password
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class PasswordChangeForm(auth_forms.PasswordChangeForm):
    """
    Cambio de contraseña, obligatorio en el primer ingreso o voluntario.

    Pide la contraseña actual y aplica la política de contraseñas. Al guardar
    apaga la marca de cambio obligatorio.
    """

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=commit)
        if commit:
            mark_password_changed(user)
        return user


class PasswordResetForm(AuthPageFormMixin, auth_forms.PasswordResetForm):
    """
    Pide el enlace de recuperación con el correo.

    La PasswordResetForm de Django solo envía el correo a usuarios activos con
    ese correo y contraseña utilizable, y no avisa si el correo no existe.
    """

    email = forms.EmailField(
        label=_("Correo electrónico"),
        max_length=254,
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )


class SetPasswordForm(AuthPageFormMixin, auth_forms.SetPasswordForm):
    """
    Nueva contraseña desde el enlace de recuperación.

    Usar el enlace demuestra que la persona es dueña del correo: al guardar se
    desbloquea la cuenta y se apaga el cambio obligatorio (SPEC 03, §6).
    """

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=commit)
        if commit:
            clear_failed_attempts(user)
            mark_password_changed(user)
        return user


# --- Gestión de usuarios (SPEC 04) -----------------------------------------


class UserFormMixin:
    """
    Campos comunes de la creación y la edición de usuarios.

    Valida con las reglas del modelo (correo único, celular, documento). Las
    reglas de negocio (rol propio, último administrador, superusuarios) las
    aplican los servicios, que la vista llama con `cleaned_data`.
    """

    fields: dict[str, forms.Field]

    def setup_user_fields(self) -> None:
        self.fields["first_name"].label = _("Nombres")
        self.fields["last_name"].label = _("Apellidos")
        for name in ("first_name", "last_name"):
            self.fields[name].required = True
        self.fields["phone"].help_text = _(
            "Opcional. Celular de 10 dígitos que empieza por 3."
        )
        self.fields["document_number"].help_text = _(
            "Opcional. Sin puntos ni espacios. Si lo escribes, elige también el tipo."
        )
        self.fields["document_type"].choices = [
            ("", _("Sin documento")),
            *DocumentType.choices,
        ]


class UserCreateForm(UserFormMixin, forms.ModelForm):
    role = forms.ChoiceField(label=_("Rol"), choices=Role.choices)

    field_order = [
        "username",
        "first_name",
        "last_name",
        "role",
        "email",
        "phone",
        "document_type",
        "document_number",
    ]

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone",
            "document_type",
            "document_number",
        )
        help_texts = {
            "username": _(
                "Con él entra al sistema y no se puede cambiar después. Letras, "
                'números, ".", "_" y "-".'
            ),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setup_user_fields()


class UserUpdateForm(UserFormMixin, forms.ModelForm):
    """
    Edición de un usuario. No incluye `username`, que no cambia.

    Si el usuario se edita a sí mismo, el rol queda deshabilitado: Django ignora
    lo que llegue en el POST para un campo deshabilitado y usa el valor inicial.
    """

    role = forms.ChoiceField(label=_("Rol"), choices=Role.choices)

    field_order = [
        "first_name",
        "last_name",
        "role",
        "email",
        "phone",
        "document_type",
        "document_number",
    ]

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "document_type",
            "document_number",
        )

    def __init__(self, *args: Any, editing_self: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setup_user_fields()
        if editing_self:
            self.fields["role"].disabled = True
            self.fields["role"].help_text = _("No puedes cambiar tu propio rol.")


class UserDeactivateForm(forms.Form):
    """Motivo obligatorio de la desactivación (SPEC 04, §3.7)."""

    reason = forms.CharField(
        label=_("Motivo"),
        max_length=DEACTIVATION_REASON_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_(
            "Obligatorio. Hasta 500 caracteres. Queda en la ficha del usuario."
        ),
    )
