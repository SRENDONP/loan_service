"""Middleware de la app de cuentas (SPEC 03 y SPEC 06)."""

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, resolve_url
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.accounts import policy

SESSION_STARTED_KEY = "_session_started_at"
LAST_ACTIVITY_KEY = "_last_activity"
# `_last_activity` se reescribe como mucho una vez por minuto (SPEC 06, §3.5).
ACTIVITY_WRITE_INTERVAL = 60

REASON_INACTIVITY = "inactivity"
REASON_MAX_DURATION = "max_duration"


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


def _now() -> int:
    """Segundos desde la época. Las pruebas lo reemplazan para mover el reloj."""
    return int(time.time())


class SessionPolicyMiddleware:
    """
    Cierra la sesión por inactividad o al llegar a su duración máxima (SPEC 06, §3.5).

    Los tiempos salen de `policy.py` en cada petición, así un cambio del
    parámetro aplica a las sesiones abiertas. Va después de
    `AuditContextMiddleware` y antes de `LoginRequiredMiddleware`.

    Trabaja en `process_view` para saber si la vista es pública
    (`@login_not_required`): una vista pública no cierra la sesión, pero sí
    cuenta como actividad.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None

        session = request.session
        now = _now()
        started = session.get(SESSION_STARTED_KEY)
        if started is None:
            # Sesión abierta antes de esta spec, o primera petición tras el login.
            session[SESSION_STARTED_KEY] = now
            session[LAST_ACTIVITY_KEY] = now
            return None

        last_activity = session.get(LAST_ACTIVITY_KEY, now)
        if getattr(view_func, "login_required", True):
            max_duration = policy.get_session_max_duration().total_seconds()
            if now - started > max_duration:
                return self.close_session(request, REASON_MAX_DURATION)
            idle_timeout = policy.get_session_idle_timeout().total_seconds()
            if now - last_activity > idle_timeout:
                return self.close_session(request, REASON_INACTIVITY)

        if (
            LAST_ACTIVITY_KEY not in session
            or now - last_activity > ACTIVITY_WRITE_INTERVAL
        ):
            session[LAST_ACTIVITY_KEY] = now
        return None

    @staticmethod
    def close_session(request: HttpRequest, reason: str) -> HttpResponse:
        """
        Cierra la sesión, avisa en el login y redirige.

        `audit_logout_reason` lo lee el receptor de `user_logged_out` para
        guardar el motivo en la auditoría (SPEC 05 y SPEC 06). Un GET vuelve a
        la ruta pedida después del login; cualquier otro método no, para no
        repetir la acción.
        """
        request.audit_logout_reason = reason
        logout(request)
        if reason == REASON_INACTIVITY:
            message = _("Tu sesión se cerró por inactividad.")
        else:
            message = _("Tu sesión llegó a su duración máxima. Ingresa de nuevo.")
        messages.info(request, message)
        if request.method == "GET":
            return redirect_to_login(request.get_full_path())
        return redirect(resolve_url(settings.LOGIN_URL))
