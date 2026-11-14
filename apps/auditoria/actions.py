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
    # Parámetros globales (SPEC 06, §3.7)
    SETTINGS_BUSINESS_UPDATED = "parametros.business_updated", _(
        "Parámetros del negocio editados"
    )
    SETTINGS_COLLECTION_UPDATED = "parametros.collection_updated", _(
        "Parámetros de cobro editados"
    )
    SETTINGS_ROUNDING_UPDATED = "parametros.rounding_updated", _(
        "Regla de redondeo editada"
    )
    SETTINGS_SECURITY_UPDATED = "parametros.security_updated", _(
        "Políticas de seguridad editadas"
    )
    # Catálogos y festivos (SPEC 07, §3.8)
    CATALOG_ITEM_CREATED = "catalogos.item_created", _("Ítem de catálogo creado")
    CATALOG_ITEM_UPDATED = "catalogos.item_updated", _("Ítem de catálogo editado")
    CATALOG_ITEM_DEACTIVATED = "catalogos.item_deactivated", _(
        "Ítem de catálogo desactivado"
    )
    CATALOG_ITEM_REACTIVATED = "catalogos.item_reactivated", _(
        "Ítem de catálogo reactivado"
    )
    HOLIDAY_CREATED = "festivos.created", _("Festivo creado")
    HOLIDAY_UPDATED = "festivos.updated", _("Festivo editado")
    HOLIDAY_DEACTIVATED = "festivos.deactivated", _("Festivo desactivado")
    HOLIDAY_REACTIVATED = "festivos.reactivated", _("Festivo reactivado")
    HOLIDAYS_LOADED = "festivos.loaded", _("Festivos oficiales cargados")
    # Productos de crédito y topes de tasa (SPEC 08, §3.6)
    PRODUCT_CREATED = "productos.created", _("Producto de crédito creado")
    PRODUCT_UPDATED = "productos.updated", _("Producto de crédito editado")
    PRODUCT_DEACTIVATED = "productos.deactivated", _("Producto de crédito desactivado")
    PRODUCT_REACTIVATED = "productos.reactivated", _("Producto de crédito reactivado")
    PRODUCT_RATE_SCHEDULED = "productos.rate_scheduled", _(
        "Tasa de producto programada"
    )
    PRODUCT_RATE_VOIDED = "productos.rate_voided", _("Tasa de producto anulada")
    RATE_CAP_VALUE_SCHEDULED = "topes.value_scheduled", _("Valor de tope programado")
    RATE_CAP_VALUE_VOIDED = "topes.value_voided", _("Valor de tope anulado")


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
    # Parámetros globales: el redondeo y el cobro cambian cómo se calcula y se
    # cobra; el negocio y las políticas de acceso, la seguridad (SPEC 06, §3.7).
    AuditAction.SETTINGS_BUSINESS_UPDATED: AuditCategory.SECURITY,
    AuditAction.SETTINGS_COLLECTION_UPDATED: AuditCategory.FINANCIAL,
    AuditAction.SETTINGS_ROUNDING_UPDATED: AuditCategory.FINANCIAL,
    AuditAction.SETTINGS_SECURITY_UPDATED: AuditCategory.SECURITY,
    # Catálogos de texto: configuración del negocio, como el grupo de negocio
    # de la SPEC 06 (SPEC 07, §3.8).
    AuditAction.CATALOG_ITEM_CREATED: AuditCategory.SECURITY,
    AuditAction.CATALOG_ITEM_UPDATED: AuditCategory.SECURITY,
    AuditAction.CATALOG_ITEM_DEACTIVATED: AuditCategory.SECURITY,
    AuditAction.CATALOG_ITEM_REACTIVATED: AuditCategory.SECURITY,
    # Festivos: cambian el calendario de cobro (SPEC 07, §3.8).
    AuditAction.HOLIDAY_CREATED: AuditCategory.FINANCIAL,
    AuditAction.HOLIDAY_UPDATED: AuditCategory.FINANCIAL,
    AuditAction.HOLIDAY_DEACTIVATED: AuditCategory.FINANCIAL,
    AuditAction.HOLIDAY_REACTIVATED: AuditCategory.FINANCIAL,
    AuditAction.HOLIDAYS_LOADED: AuditCategory.FINANCIAL,
    # Productos, tasas y topes: cambian lo que se cobra (SPEC 08, §3.6). Los
    # tipos de tope usan las acciones `catalogos.*`.
    AuditAction.PRODUCT_CREATED: AuditCategory.FINANCIAL,
    AuditAction.PRODUCT_UPDATED: AuditCategory.FINANCIAL,
    AuditAction.PRODUCT_DEACTIVATED: AuditCategory.FINANCIAL,
    AuditAction.PRODUCT_REACTIVATED: AuditCategory.FINANCIAL,
    AuditAction.PRODUCT_RATE_SCHEDULED: AuditCategory.FINANCIAL,
    AuditAction.PRODUCT_RATE_VOIDED: AuditCategory.FINANCIAL,
    AuditAction.RATE_CAP_VALUE_SCHEDULED: AuditCategory.FINANCIAL,
    AuditAction.RATE_CAP_VALUE_VOIDED: AuditCategory.FINANCIAL,
}
