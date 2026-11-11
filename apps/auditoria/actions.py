"""
Catálogo único de acciones auditables (SPEC 05, §3.1).

Cada spec que crea un módulo agrega aquí sus acciones y la categoría de cada
una en `ACTION_CATEGORIES`. La categoría la decide este catálogo, no quien
llama a `record`. El valor de una acción no se cambia nunca después de usarse,
porque los registros guardados lo referencian; la etiqueta sí puede cambiar.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditCategory(models.TextChoices):
    ACCESS = "access", _("Acceso")
    SECURITY = "security", _("Seguridad")
    PERSONAL_DATA = "personal_data", _("Datos personales")
    FINANCIAL = "financial", _("Operación financiera")


class AuditAction(models.TextChoices):
    # Acceso
    LOGIN_SUCCEEDED = "auth.login_succeeded", _("Ingreso exitoso")
    LOGIN_FAILED = "auth.login_failed", _("Ingreso fallido")
    LOGIN_BLOCKED = "auth.login_blocked", _("Intento durante un bloqueo")
    ACCOUNT_LOCKED = "auth.account_locked", _("Cuenta bloqueada por intentos fallidos")
    LOGOUT = "auth.logout", _("Cierre de sesión")
    PASSWORD_CHANGED = "auth.password_changed", _("Cambio de contraseña")
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested", _(
        "Solicitud de recuperación de contraseña"
    )
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed", _(
        "Contraseña restablecida con el enlace"
    )
    # Seguridad
    USER_CREATED = "users.created", _("Usuario creado")
    USER_UPDATED = "users.updated", _("Usuario editado")
    USER_DEACTIVATED = "users.deactivated", _("Usuario desactivado")
    USER_REACTIVATED = "users.reactivated", _("Usuario reactivado")
    USER_UNLOCKED = "users.unlocked", _("Usuario desbloqueado")
    USER_PASSWORD_RESET = "users.password_reset", _(
        "Contraseña restablecida por un administrador"
    )
    USER_SESSIONS_CLOSED = "users.sessions_closed", _(
        "Sesiones cerradas por un administrador"
    )


ACTION_CATEGORIES: dict[AuditAction, AuditCategory] = {
    # Acceso
    AuditAction.LOGIN_SUCCEEDED: AuditCategory.ACCESS,
    AuditAction.LOGIN_FAILED: AuditCategory.ACCESS,
    AuditAction.LOGIN_BLOCKED: AuditCategory.ACCESS,
    AuditAction.ACCOUNT_LOCKED: AuditCategory.ACCESS,
    AuditAction.LOGOUT: AuditCategory.ACCESS,
    AuditAction.PASSWORD_CHANGED: AuditCategory.ACCESS,
    AuditAction.PASSWORD_RESET_REQUESTED: AuditCategory.ACCESS,
    AuditAction.PASSWORD_RESET_COMPLETED: AuditCategory.ACCESS,
    # Seguridad
    AuditAction.USER_CREATED: AuditCategory.SECURITY,
    AuditAction.USER_UPDATED: AuditCategory.SECURITY,
    AuditAction.USER_DEACTIVATED: AuditCategory.SECURITY,
    AuditAction.USER_REACTIVATED: AuditCategory.SECURITY,
    AuditAction.USER_UNLOCKED: AuditCategory.SECURITY,
    AuditAction.USER_PASSWORD_RESET: AuditCategory.SECURITY,
    AuditAction.USER_SESSIONS_CLOSED: AuditCategory.SECURITY,
}
