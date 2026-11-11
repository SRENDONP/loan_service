"""Middleware de la app de cuentas (SPEC 03)."""

from collections.abc import Callable
from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """
    Lleva a la pantalla de cambio de contraseña a quien debe cambiarla.

    Mientras `must_change_password` sea verdadero, cualquier ruta redirige a
    `accounts:password_change`, salvo esa misma, el cierre de sesión, los
    estáticos y el healthcheck. Va después de LoginRequiredMiddleware.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
            and not self.is_allowed(request.path)
        ):
            return redirect("accounts:password_change")
        return self.get_response(request)

    @staticmethod
    def is_allowed(path: str) -> bool:
        """Rutas que siguen disponibles mientras el cambio está pendiente."""
        allowed = {
            reverse("accounts:password_change"),
            reverse("accounts:logout"),
            reverse("core:health"),
        }
        static_prefix = urlsplit(settings.STATIC_URL).path
        return path in allowed or (
            bool(static_prefix) and path.startswith(static_prefix)
        )
