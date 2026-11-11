"""
Contexto de la petición para la auditoría (SPEC 05, §3.4 y §3.5).

`AuditContextMiddleware` fija el contexto de cada petición y `audit_context`
lo fija en los comandos de gestión. `record` lo lee con `get_context()`, así
los servicios no necesitan recibir el `request`. El estado vive en un
`ContextVar`, que no se cruza entre hilos ni entre peticiones.
"""

import ipaddress
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.urls import NoReverseMatch, reverse

from apps.auditoria.models import AuditSource

USER_AGENT_MAX_LENGTH = 255
REQUEST_PATH_MAX_LENGTH = 255
REQUEST_METHOD_MAX_LENGTH = 10


@dataclass(frozen=True)
class AuditContext:
    source: AuditSource = AuditSource.SYSTEM
    ip_address: str | None = None
    user_agent: str = ""
    request_method: str = ""
    request_path: str = ""
    request_id: uuid.UUID | None = None


_DEFAULT_CONTEXT = AuditContext()

_current: ContextVar[AuditContext] = ContextVar("auditoria_context")


def get_context() -> AuditContext:
    """El contexto actual, o el de por defecto (origen `system`, sin IP)."""
    return _current.get(_DEFAULT_CONTEXT)


@contextmanager
def use_context(context: AuditContext) -> Iterator[AuditContext]:
    """Fija `context` dentro del bloque y restablece el anterior al salir."""
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)


@contextmanager
def audit_context(**fields: Any) -> Iterator[AuditContext]:
    """
    Fija un contexto armado con `fields` dentro del bloque.

    Los comandos de gestión lo usan con `source=AuditSource.COMMAND`.
    """
    with use_context(AuditContext(**fields)) as context:
        yield context


def context_from_request(request: HttpRequest) -> AuditContext:
    """
    Arma el contexto de una petición.

    La ruta no lleva la cadena de consulta, para no guardar tokens. Cada
    petición recibe un `request_id` nuevo.
    """
    return AuditContext(
        source=_source_for_path(request.path),
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_MAX_LENGTH],
        request_method=(request.method or "")[:REQUEST_METHOD_MAX_LENGTH],
        request_path=request.path[:REQUEST_PATH_MAX_LENGTH],
        request_id=uuid.uuid4(),
    )


def get_client_ip(request: HttpRequest) -> str | None:
    """
    La IP del cliente (§3.5).

    Con `AUDIT_TRUSTED_PROXIES = 0` se usa `REMOTE_ADDR` y se ignora
    `X-Forwarded-For`, que el cliente puede falsificar. Con `N > 0` se toma la
    entrada número `N` de `X-Forwarded-For` contando desde la derecha, o
    `REMOTE_ADDR` si la cabecera tiene menos entradas. Un valor que no es una
    IP válida se devuelve como `None`.
    """
    candidate = request.META.get("REMOTE_ADDR", "")
    trusted_proxies = getattr(settings, "AUDIT_TRUSTED_PROXIES", 0)
    if trusted_proxies > 0:
        header = request.META.get("HTTP_X_FORWARDED_FOR", "")
        entries = [entry.strip() for entry in header.split(",")] if header else []
        if len(entries) >= trusted_proxies:
            candidate = entries[-trusted_proxies]
    return _valid_ip(candidate)


def _valid_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _source_for_path(path: str) -> AuditSource:
    try:
        admin_prefix = reverse("admin:index")
    except NoReverseMatch:
        return AuditSource.WEB
    return AuditSource.ADMIN if path.startswith(admin_prefix) else AuditSource.WEB
