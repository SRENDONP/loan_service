"""Registro del usuario en el admin de Django (SPEC 03 y SPEC 04)."""

from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import forms as auth_forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


class UserCreationForm(auth_forms.AdminUserCreationForm):
    """El formulario de Django está atado a `auth.User`; aquí usa el propio."""

    class Meta(auth_forms.AdminUserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class UserChangeForm(auth_forms.UserChangeForm):
    class Meta(auth_forms.UserChangeForm.Meta):
        model = User


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    """
    Usuarios en el admin, con los campos del bloqueo y del cambio obligatorio.

    Un usuario creado aquí debe cambiar la contraseña en su primer ingreso
    (`must_change_password` vale True por defecto). Los usuarios no se borran,
    solo se desactivan (§6.3), así que el admin no ofrece el borrado.
    """

    form = UserChangeForm
    add_form = UserCreationForm

    fieldsets = (
        *auth_admin.UserAdmin.fieldsets,
        (
            _("Contacto e identificación"),
            {"fields": ("phone", "document_type", "document_number")},
        ),
        (
            _("Desactivación"),
            {
                "fields": (
                    "deactivated_at",
                    "deactivated_by",
                    "deactivation_reason",
                ),
            },
        ),
        (
            _("Acceso"),
            {
                "fields": (
                    "must_change_password",
                    "failed_login_attempts",
                    "locked_until",
                ),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_superuser",
        "must_change_password",
        "locked_until",
    )
    list_filter = (
        "is_superuser",
        "is_active",
        "must_change_password",
        "groups",
    )

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
