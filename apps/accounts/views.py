"""Vistas de autenticación (SPEC 03)."""

from django.contrib import messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _

from apps.accounts.forms import LoginForm, PasswordChangeForm, SetPasswordForm
from apps.accounts.tokens import password_reset_token_generator


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
        response = super().form_valid(form)
        messages.success(self.request, _("Cambiaste tu contraseña."))
        return response


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
