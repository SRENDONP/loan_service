"""Vistas de autenticación (SPEC 03) y de gestión de usuarios (SPEC 04)."""

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.cache import add_never_cache_headers
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.generic import DetailView, FormView, TemplateView, View

from apps.accounts.forms import (
    LoginForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreateForm,
    UserDeactivateForm,
    UserUpdateForm,
)
from apps.accounts.models import User
from apps.accounts.permissions import PermissionRequiredMixin
from apps.accounts.roles import Role, get_role
from apps.accounts.services import (
    create_user,
    deactivate_user,
    find_user_by_identifier,
    logout_user_sessions,
    reactivate_user,
    reset_user_password,
    unlock_user,
    update_user,
)
from apps.accounts.tokens import password_reset_token_generator
from apps.auditoria.actions import AuditAction
from apps.auditoria.services import diff, record, snapshot
from apps.parametros.formatting import format_datetime as parametros_format_datetime


@method_decorator(login_not_required, name="dispatch")
class LoginView(auth_views.LoginView):
    """
    Inicio de sesión propio, con usuario o correo.

    La validación de `next` (que no lleve a otro dominio) es la de LoginView de
    Django.
    """

    form_class = LoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Cierre de sesión, solo por POST (LogoutView de Django responde 405 a GET)."""

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        response = super().post(request, *args, **kwargs)
        messages.success(request, _("Cerraste sesión."))
        return response


class PasswordChangeView(auth_views.PasswordChangeView):
    """
    Cambio de contraseña, el obligatorio del primer ingreso y el voluntario.

    La PasswordChangeView de Django actualiza el hash de la sesión: la sesión
    actual sigue abierta y las demás sesiones del usuario quedan invalidadas.
    """

    form_class = PasswordChangeForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("core:home")

    def form_valid(self, form: PasswordChangeForm) -> HttpResponse:
        user = form.user
        forced = user.must_change_password
        before = snapshot(user, ["password"])
        # El cambio y su registro de auditoría van juntos (SPEC 05, §3.7).
        with transaction.atomic():
            response = super().form_valid(form)
            record(
                AuditAction.PASSWORD_CHANGED,
                actor=user,
                target=user,
                changes=diff(before, snapshot(user, ["password"])),
                extra={"forced": forced},
            )
        messages.success(self.request, _("Cambiaste tu contraseña."))
        return response


@method_decorator(login_not_required, name="dispatch")
class PasswordResetView(auth_views.PasswordResetView):
    """
    Pide el enlace de recuperación con el correo.

    Registra la solicitud exista o no el correo (SPEC 05, §3.7). La respuesta
    es la misma en los dos casos, para no revelar qué correos existen.
    """

    form_class = PasswordResetForm
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/email/password_reset_email.txt"
    subject_template_name = "accounts/email/password_reset_subject.txt"
    token_generator = password_reset_token_generator
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form: PasswordResetForm) -> HttpResponse:
        email = form.cleaned_data["email"]
        # Se registra antes de enviar: si la auditoría falla, no sale el correo.
        record(
            AuditAction.PASSWORD_RESET_REQUESTED,
            target=find_user_by_identifier(email),
            identifier=email,
        )
        return super().form_valid(form)


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """
    Nueva contraseña desde el enlace de recuperación.

    Usa el generador de tokens con la vigencia de `policy.py`. No inicia sesión
    al terminar: la persona entra con su nueva contraseña desde el login.
    """

    form_class = SetPasswordForm
    template_name = "accounts/password_reset_confirm.html"
    token_generator = password_reset_token_generator
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form: SetPasswordForm) -> HttpResponse:
        user = form.user
        before = snapshot(user, ["password"])
        with transaction.atomic():
            response = super().form_valid(form)
            record(
                AuditAction.PASSWORD_RESET_COMPLETED,
                actor=user,
                target=user,
                changes=diff(before, snapshot(user, ["password"])),
            )
        return response


@login_not_required
def admin_login_redirect(request: HttpRequest) -> HttpResponse:
    """
    Reemplaza el login del admin de Django por el login propio.

    Así el admin no tiene un camino que salte el bloqueo ni el cambio
    obligatorio. A un usuario con sesión que no es superusuario se le responde
    403: redirigirlo al login lo devolvería al admin en un bucle.
    """
    if request.user.is_authenticated and not request.user.is_superuser:
        raise PermissionDenied
    next_url = request.GET.get(REDIRECT_FIELD_NAME, reverse("admin:index"))
    return redirect_to_login(next_url)


# --- Gestión de usuarios (SPEC 04, §3.6 y §3.7) ----------------------------

STATUS_DISPLAY = {
    "active": (gettext_lazy("Activo"), "badge-success"),
    "locked": (gettext_lazy("Bloqueado"), "badge-warning"),
    "inactive": (gettext_lazy("Inactivo"), "badge-secondary"),
}


def users_with_groups() -> QuerySet:
    """Usuarios con sus grupos precargados, para leer el rol sin N+1."""
    return User.objects.prefetch_related("groups").select_related("deactivated_by")


def role_of(user: User) -> Role | None:
    """El rol a partir de los grupos precargados (ver `users_with_groups`)."""
    for group in user.groups.all():
        if group.name in Role.values:
            return Role(group.name)
    return None


def role_badge(user: User) -> SafeString:
    """El rol como badge; los superusuarios llevan el suyo propio."""
    if user.is_superuser:
        return format_html(
            '<span class="badge badge-dark">{}</span>', _("Superusuario")
        )
    role = role_of(user)
    if role is None:
        return format_html('<span class="badge badge-light">{}</span>', _("Sin rol"))
    return format_html('<span class="badge badge-primary">{}</span>', role.label)


def status_badge(user: User) -> SafeString:
    label, css = STATUS_DISPLAY[user.status]
    return format_html('<span class="badge {}">{}</span>', css, label)


def format_datetime(value) -> str:
    """La fecha y hora con el formato de los parámetros globales (SPEC 06)."""
    if value is None:
        return _("Nunca")
    return parametros_format_datetime(value)


class UserListView(PermissionRequiredMixin, TemplateView):
    """Listado de usuarios con DataTables. Solo para el Administrador."""

    permission_required = "accounts.view_user"
    template_name = "accounts/users/list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users = users_with_groups().order_by("username")
        context.update(
            table_title=_("Usuarios del sistema"),
            table_columns=[
                _("Usuario"),
                _("Nombre"),
                _("Rol"),
                _("Estado"),
                _("Último ingreso"),
                _("Acciones"),
            ],
            table_rows=[self.row(user) for user in users],
        )
        return context

    def row(self, user: User) -> list:
        detail_url = reverse("accounts:user_detail", args=[user.pk])
        actions = ""
        if not user.is_superuser:
            actions = format_html(
                '<a href="{}" class="btn btn-sm btn-light">{}</a>',
                detail_url,
                _("Ver ficha"),
            )
        return [
            format_html('<a href="{}">{}</a>', detail_url, user.username),
            user.get_full_name() or "—",
            role_badge(user),
            status_badge(user),
            format_datetime(user.last_login),
            actions,
        ]


class UserDetailView(PermissionRequiredMixin, DetailView):
    """Ficha de un usuario. Los superusuarios se ven, pero sin acciones."""

    permission_required = "accounts.view_user"
    template_name = "accounts/users/detail.html"
    context_object_name = "target"

    def get_queryset(self) -> QuerySet:
        return users_with_groups()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        target: User = self.object
        context.update(
            role_badge=role_badge(target),
            status_badge=status_badge(target),
            last_login_display=format_datetime(target.last_login),
            locked_until_display=(
                format_datetime(target.locked_until)
                if target.status == "locked"
                else None
            ),
            is_self=target.pk == self.request.user.pk,
            show_actions=(
                not target.is_superuser and target.pk != self.request.user.pk
            ),
            deactivated_at_display=(
                format_datetime(target.deactivated_at) if target.deactivated_at else "—"
            ),
        )
        return context


def temporary_password_response(
    request: HttpRequest, target: User, password: str, *, heading: str
) -> HttpResponse:
    """
    Muestra la contraseña temporal una sola vez (SPEC 04, §3.6).

    Se renderiza desde el POST, sin redirección: la contraseña no pasa por
    `messages` ni por la sesión. `no-store` impide que el navegador la guarde.
    """
    response = render(
        request,
        "accounts/users/temporary_password.html",
        {"target": target, "password": password, "heading": heading},
    )
    add_never_cache_headers(response)
    return response


class UserTargetMixin:
    """
    Carga al usuario de la URL y aparta a los superusuarios.

    Va después de `PermissionRequiredMixin` en las bases de la vista, para que
    el permiso se verifique antes de buscar al usuario. Si el usuario es
    superusuario, vuelve a la ficha con un aviso: no se gestiona desde la
    aplicación. Los servicios aplican la misma regla.
    """

    request: HttpRequest
    target: User

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.target = get_object_or_404(users_with_groups(), pk=kwargs["pk"])
        if self.target.is_superuser:
            messages.error(
                request, _("Los superusuarios no se gestionan desde la aplicación.")
            )
            return redirect("accounts:user_detail", pk=self.target.pk)
        return super().dispatch(request, *args, **kwargs)


class UserCreateView(PermissionRequiredMixin, FormView):
    """Crea un usuario con su rol y muestra su contraseña temporal."""

    permission_required = "accounts.add_user"
    template_name = "accounts/users/form.html"
    form_class = UserCreateForm
    extra_context = {"creating": True}

    def form_valid(self, form: UserCreateForm) -> HttpResponse:
        data = form.cleaned_data
        try:
            target, password = create_user(
                self.request.user, data=data, role=data["role"]
            )
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(
            self.request, _("Creaste el usuario %(username)s.") % {"username": target}
        )
        return temporary_password_response(
            self.request, target, password, heading=_("Usuario creado")
        )


class UserUpdateView(PermissionRequiredMixin, UserTargetMixin, FormView):
    """
    Edita los datos y el rol de un usuario. El `username` no cambia.

    Un superusuario no se edita desde aquí: se vuelve a la ficha con un aviso.
    """

    permission_required = "accounts.change_user"
    template_name = "accounts/users/form.html"
    form_class = UserUpdateForm
    extra_context = {"creating": False}

    def get_form_kwargs(self) -> dict:
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.target
        kwargs["editing_self"] = self.target.pk == self.request.user.pk
        return kwargs

    def get_initial(self) -> dict:
        role = get_role(self.target)
        return {"role": role.value if role else None}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target"] = self.target
        return context

    def form_valid(self, form: UserUpdateForm) -> HttpResponse:
        data = form.cleaned_data
        try:
            update_user(self.request.user, self.target, data=data, role=data["role"])
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        messages.success(self.request, _("Guardaste los cambios del usuario."))
        return redirect("accounts:user_detail", pk=self.target.pk)


class UserDeactivateView(PermissionRequiredMixin, UserTargetMixin, FormView):
    """Pide el motivo y desactiva al usuario. Sus sesiones se cierran."""

    permission_required = "accounts.deactivate_user"
    template_name = "accounts/users/deactivate.html"
    form_class = UserDeactivateForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target"] = self.target
        return context

    def form_valid(self, form: UserDeactivateForm) -> HttpResponse:
        try:
            deactivate_user(
                self.request.user, self.target, reason=form.cleaned_data["reason"]
            )
        except ValidationError as error:
            messages.error(self.request, " ".join(error.messages))
        else:
            messages.success(
                self.request,
                _("Desactivaste a %(username)s y se cerraron sus sesiones.")
                % {"username": self.target.username},
            )
        return redirect("accounts:user_detail", pk=self.target.pk)


class UserActionView(PermissionRequiredMixin, UserTargetMixin, View):
    """
    Base de las acciones de la ficha que no tienen formulario. Solo aceptan POST.

    Si un servicio rechaza la acción por una regla, se vuelve a la ficha con el
    mensaje del error y sin cambios.
    """

    http_method_names = ["post"]

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        try:
            response = self.perform()
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
            response = None
        return response or redirect("accounts:user_detail", pk=self.target.pk)

    def perform(self) -> HttpResponse | None:
        raise NotImplementedError


class UserReactivateView(UserActionView):
    permission_required = "accounts.deactivate_user"

    def perform(self) -> None:
        reactivate_user(self.request.user, self.target)
        messages.success(
            self.request,
            _(
                "Reactivaste a %(username)s. Debe cambiar la contraseña en su "
                "próximo ingreso."
            )
            % {"username": self.target.username},
        )


class UserUnlockView(UserActionView):
    permission_required = "accounts.unlock_user"

    def perform(self) -> None:
        was_locked = self.target.status == "locked"
        unlock_user(self.request.user, self.target)
        if was_locked:
            messages.success(
                self.request,
                _("Desbloqueaste a %(username)s.") % {"username": self.target.username},
            )
        else:
            messages.info(self.request, _("La cuenta no estaba bloqueada."))


class UserResetPasswordView(UserActionView):
    permission_required = "accounts.reset_user_password"

    def perform(self) -> HttpResponse:
        password = reset_user_password(self.request.user, self.target)
        messages.success(
            self.request,
            _("Restableciste la contraseña de %(username)s y se cerraron sus sesiones.")
            % {"username": self.target.username},
        )
        return temporary_password_response(
            self.request,
            self.target,
            password,
            heading=_("Contraseña restablecida"),
        )


class UserLogoutSessionsView(UserActionView):
    permission_required = "accounts.logout_user_sessions"

    def perform(self) -> None:
        closed = logout_user_sessions(self.request.user, self.target)
        if closed == 0:
            messages.info(
                self.request,
                _("%(username)s no tenía sesiones abiertas.")
                % {"username": self.target.username},
            )
            return
        messages.success(
            self.request,
            ngettext(
                "Cerraste %(count)d sesión de %(username)s.",
                "Cerraste %(count)d sesiones de %(username)s.",
                closed,
            )
            % {"count": closed, "username": self.target.username},
        )
