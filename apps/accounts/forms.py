"""Formularios de autenticación (SPEC 03)."""

from typing import Any

from django import forms
from django.contrib.auth import forms as auth_forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.services import (
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
