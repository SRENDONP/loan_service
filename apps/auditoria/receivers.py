"""
Receptores de las señales de autenticación de Django (SPEC 05, §3.7 y ADR-004).

Cubren cualquier camino de ingreso, incluido el del admin. Solo llaman a
`record`: no hay reglas de negocio aquí. El bloqueo, el intento durante un
bloqueo y los cambios de contraseña no tienen señal de Django y se auditan
explícitamente desde los servicios y las vistas de `apps.accounts`.
"""

from typing import Any

from django.http import HttpRequest

from apps.accounts.services import find_user_by_identifier
from apps.auditoria.actions import AuditAction
from apps.auditoria.services import record


def audit_login_succeeded(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    record(AuditAction.LOGIN_SUCCEEDED, actor=user, target=user)


def audit_login_failed(
    sender: Any,
    credentials: dict[str, Any],
    request: HttpRequest | None = None,
    **kwargs: Any,
) -> None:
    """
    Registra el fallo con el texto escrito.

    Django entrega las credenciales con la contraseña ya enmascarada; aquí solo
    se toma `username`. La entidad es el usuario que corresponde a ese texto,
    si existe.
    """
    identifier = str(credentials.get("username") or "")
    record(
        AuditAction.LOGIN_FAILED,
        target=find_user_by_identifier(identifier),
        identifier=identifier,
    )


def audit_logout(
    sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any
) -> None:
    # Cerrar sesión sin tenerla abierta no deja registro.
    if user is None:
        return
    # El cierre automático (inactividad o duración máxima) deja su motivo en la
    # petición (SPEC 06, §3.5). El cierre voluntario no lleva `extra`.
    reason = getattr(request, "audit_logout_reason", None)
    extra = {"reason": reason} if reason else None
    record(AuditAction.LOGOUT, actor=user, target=user, extra=extra)
