"""
Utilidades para verificar permisos en vistas y servicios (SPEC 04, §3.4).

Ocultar una entrada del menú no protege nada: cada vista y cada servicio
sensible verifica sus permisos con estas utilidades (§6.2 y §6.3). Como todo el
sistema exige sesión (`LoginRequiredMiddleware`), un usuario sin permiso recibe
un 403 y nunca una redirección al login.
"""

from collections.abc import Callable
from typing import Any

from django.contrib.auth import decorators as auth_decorators
from django.contrib.auth import mixins as auth_mixins
from django.core.exceptions import PermissionDenied


def require_perms(user: Any, *perms: str) -> None:
    """Lanza `PermissionDenied` si al usuario le falta alguno de los permisos."""
    if not perms:
        raise ValueError("require_perms necesita al menos un permiso.")
    if not user.has_perms(perms):
        raise PermissionDenied


class PermissionRequiredMixin(auth_mixins.PermissionRequiredMixin):
    """El mixin de Django, pero responde 403 en vez de redirigir al login."""

    raise_exception = True


def permission_required(*perms: str) -> Callable[[Callable], Callable]:
    """El decorador de Django para vistas de función, con 403 en vez de redirigir."""
    if not perms:
        raise ValueError("permission_required necesita al menos un permiso.")
    return auth_decorators.permission_required(perms, raise_exception=True)
