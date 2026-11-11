"""Excepciones de la auditoría (SPEC 05, §3.3)."""

from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _


class ImmutableAuditEventError(PermissionDenied):
    """Se intentó editar o borrar un registro de auditoría."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message or _("Los registros de auditoría no se pueden editar ni borrar.")
        )
