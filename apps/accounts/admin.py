"""Registro del usuario en el admin de Django (SPEC 03 y SPEC 04)."""

from django.contrib import admin
from django.contrib.admin.utils import unquote
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import forms as auth_forms
from django.db import router, transaction
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.services import PROFILE_FIELDS, user_audit_snapshot
from apps.auditoria.actions import AuditAction
from apps.auditoria.services import diff, record


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

    # --- Auditoría (SPEC 05, §3.7) ---------------------------------------------
    #
    # El admin es una puerta trasera para superusuarios y no debe quedar ciega.
    # Crear y editar corren dentro de la transacción del admin de Django, así
    # que un fallo de `record` también revierte el cambio.

    def save_model(self, request: HttpRequest, obj: User, form, change: bool) -> None:
        # El formulario ya aplicó los cambios a `obj`: el "antes" sale de la base.
        form._audit_before = (
            user_audit_snapshot(User.objects.get(pk=obj.pk)) if change else None
        )
        super().save_model(request, obj, form, change)

    def save_related(self, request: HttpRequest, form, formsets, change: bool) -> None:
        # Los grupos se guardan aquí, así que el rol se compara después.
        super().save_related(request, form, formsets, change)
        user = form.instance
        before = getattr(form, "_audit_before", None)
        if before is None:
            record(
                AuditAction.USER_CREATED,
                actor=request.user,
                target=user,
                changes=diff({}, user_audit_snapshot(user, PROFILE_FIELDS)),
            )
            return
        changes = diff(before, user_audit_snapshot(user))
        if changes:
            record(
                AuditAction.USER_UPDATED,
                actor=request.user,
                target=user,
                changes=changes,
            )

    def user_change_password(
        self, request: HttpRequest, id: str, form_url: str = ""
    ) -> HttpResponse:
        # La vista de Django no abre una transacción; aquí sí, para que el
        # cambio y su registro vayan juntos.
        with transaction.atomic(using=router.db_for_write(self.model)):
            user = self.get_object(request, unquote(id))
            before = user_audit_snapshot(user) if user is not None else None
            response = super().user_change_password(request, id, form_url)
            if before is not None and request.method == "POST":
                user.refresh_from_db()
                changes = diff(before, user_audit_snapshot(user))
                if "password" in changes:
                    record(
                        AuditAction.USER_PASSWORD_RESET,
                        actor=request.user,
                        target=user,
                        changes=changes,
                    )
        return response
