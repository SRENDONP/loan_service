"""
Roles del sistema y sus permisos (SPEC 04, §3.1 y ADR-002).

`ROLE_PERMISSIONS` es la única fuente de verdad de qué puede hacer cada rol.
Una spec que crea un módulo agrega aquí los permisos de sus modelos, y
`sync_roles` deja los cuatro grupos de Django exactamente iguales a este mapa.
Los grupos no se editan a mano: cualquier cambio manual se revierte en el
siguiente `migrate`.
"""

from typing import Any

from django.apps import AppConfig, apps
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """Los cuatro roles de la §6.2. El valor es el nombre exacto del grupo."""

    ADMINISTRATOR = "Administrador", _("Administrador")
    SUPERVISOR = "Supervisor", _("Supervisor")
    COLLECTOR = "Cajero/Cobrador", _("Cajero/Cobrador")
    VIEWER = "Consulta", _("Consulta")


USER_MANAGEMENT_PERMISSIONS = frozenset(
    {
        "accounts.view_user",
        "accounts.add_user",
        "accounts.change_user",
        "accounts.deactivate_user",
        "accounts.unlock_user",
        "accounts.reset_user_password",
        "accounts.logout_user_sessions",
    }
)

# Parámetros globales (SPEC 06, §3.8). Solo el Administrador los ve y los edita;
# el resto del sistema los lee por el servicio, sin permisos.
PARAMETROS_PERMISSIONS = frozenset(
    {
        "parametros.view_globalsettings",
        "parametros.change_globalsettings",
    }
)

# Catálogos y festivos (SPEC 07, §3.9): ver, crear y editar los siete modelos.
# No existe el permiso `delete`: los ítems y los festivos se desactivan. El resto
# del sistema lee los ítems activos por el servicio, sin permisos.
CATALOG_PERMISSIONS = frozenset(
    f"parametros.{action}_{model}"
    for model in (
        "documenttype",
        "occupation",
        "creditpurpose",
        "voidreason",
        "rejectionreason",
        "thirdpartyrelationtype",
        "holiday",
    )
    for action in ("view", "add", "change")
)

# Productos de crédito y topes de tasa (SPEC 08, §3.7). El Administrador ve,
# crea, edita, programa y anula; el Supervisor y Consulta solo ven. Sin `delete`:
# los productos y los tipos se desactivan, y las versiones se anulan. El
# Cajero/Cobrador no tiene pantalla: el simulador le ofrecerá los productos por
# el servicio, sin permisos.
PRODUCT_MODELS = ("creditproduct", "productrateversion", "ratecaptype", "ratecapvalue")

PRODUCT_PERMISSIONS = frozenset(
    f"parametros.{action}_{model}"
    for model in PRODUCT_MODELS
    for action in ("view", "add", "change")
)
PRODUCT_VIEW_PERMISSIONS = frozenset(
    f"parametros.view_{model}" for model in PRODUCT_MODELS
)

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMINISTRATOR: (
        USER_MANAGEMENT_PERMISSIONS
        | PARAMETROS_PERMISSIONS
        | CATALOG_PERMISSIONS
        | PRODUCT_PERMISSIONS
    ),
    Role.SUPERVISOR: PRODUCT_VIEW_PERMISSIONS,
    Role.COLLECTOR: frozenset(),
    Role.VIEWER: PRODUCT_VIEW_PERMISSIONS,
}


def get_role(user: Any) -> Role | None:
    """
    El rol del usuario según su grupo, o `None` si no tiene ninguno.

    Un superusuario creado por consola no tiene rol. Los servicios garantizan
    que un usuario tenga a lo sumo un rol.
    """
    if not getattr(user, "pk", None):
        return None
    name = (
        user.groups.filter(name__in=Role.values)
        .order_by("name")
        .values_list("name", flat=True)
        .first()
    )
    return Role(name) if name is not None else None


def has_role(user: Any, role: Role) -> bool:
    """Indica si el usuario tiene ese rol."""
    return get_role(user) == role


def sync_roles(*, using: str = "default") -> None:
    """
    Deja los cuatro grupos con exactamente los permisos de `ROLE_PERMISSIONS`.

    Crea los grupos que falten, agrega los permisos que faltan y quita los que
    sobran. No toca otros grupos ni los permisos individuales de los usuarios.
    Es idempotente. Si un permiso del mapa no existe en la base de datos, lanza
    `ImproperlyConfigured` sin cambiar nada.
    """
    wanted = {
        role: _resolve_permissions(perms, using)
        for role, perms in ROLE_PERMISSIONS.items()
    }
    for role, permissions in wanted.items():
        group, _created = Group.objects.using(using).get_or_create(name=role.value)
        group.permissions.set(permissions)


def _resolve_permissions(perms: frozenset[str], using: str) -> list[Permission]:
    """Convierte `"app_label.codename"` en permisos, o falla si alguno no existe."""
    if not perms:
        return []
    query = Q()
    for perm in perms:
        app_label, _sep, codename = perm.partition(".")
        query |= Q(content_type__app_label=app_label, codename=codename)
    found = list(
        Permission.objects.using(using).filter(query).select_related("content_type")
    )
    missing = perms - {f"{p.content_type.app_label}.{p.codename}" for p in found}
    if missing:
        raise ImproperlyConfigured(
            "ROLE_PERMISSIONS usa permisos que no existen: "
            + ", ".join(sorted(missing))
        )
    return found


def _last_app_with_models() -> AppConfig:
    """La última app de INSTALLED_APPS que tiene modelos."""
    return [config for config in apps.get_app_configs() if config.models_module][-1]


def sync_roles_after_migrate(
    sender: AppConfig, using: str = "default", **kwargs: Any
) -> None:
    """
    Receptor de `post_migrate` (ADR-002).

    Django emite `post_migrate` una vez por cada app con modelos, en el orden
    de INSTALLED_APPS, y crea los permisos de cada app en esa misma señal. Por
    eso solo se sincroniza con la señal de la última app: en ese momento ya
    existen todos los permisos del proyecto.
    """
    if sender.label != _last_app_with_models().label:
        return
    sync_roles(using=using)
