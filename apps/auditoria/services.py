"""
Servicio de auditoría (SPEC 05, §3.6).

Cada servicio de negocio llama a `record` dentro de su propia transacción, con
el actor que ya recibe. `record` no abre otra transacción ni atrapa errores:
si la escritura falla, la operación completa se revierte.

Para auditar una edición, el servicio toma un `snapshot` antes y otro después
y pasa el `diff` como `changes`.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.auditoria.actions import ACTION_CATEGORIES, AuditAction
from apps.auditoria.context import get_context
from apps.auditoria.models import AuditEvent

if TYPE_CHECKING:
    from apps.accounts.models import User

# Campos cuyo valor nunca se guarda. Cada spec agrega aquí sus campos secretos.
SENSITIVE_FIELDS = frozenset({"password"})

HIDDEN = "[oculto]"

IDENTIFIER_MAX_LENGTH = 150
OBJECT_REPR_MAX_LENGTH = 200


def record(
    action: AuditAction,
    *,
    actor: User | None = None,
    target: models.Model | None = None,
    changes: Mapping[str, Sequence[Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
    identifier: str = "",
) -> AuditEvent:
    """
    Crea un registro de auditoría en la transacción de quien llama.

    La categoría sale de `ACTION_CATEGORIES` y el origen, la IP y los datos de
    la petición, de `get_context()`. Lanza `ValueError` si la acción no está en
    el catálogo.
    """
    action, category = _resolve_action(action)
    context = get_context()

    content_type = None
    object_id = ""
    object_repr = ""
    if target is not None:
        content_type = ContentType.objects.get_for_model(target)
        object_id = str(target.pk)
        object_repr = str(target)[:OBJECT_REPR_MAX_LENGTH]

    return AuditEvent.objects.create(
        category=category,
        action=action,
        source=context.source,
        actor=actor,
        actor_username=actor.get_username() if actor is not None else "",
        identifier=identifier[:IDENTIFIER_MAX_LENGTH],
        content_type=content_type,
        object_id=object_id,
        object_repr=object_repr,
        changes=_hide_sensitive(
            {field: list(values) for field, values in (changes or {}).items()}
        ),
        extra=_hide_sensitive(dict(extra or {})),
        ip_address=context.ip_address,
        user_agent=context.user_agent,
        request_method=context.request_method,
        request_path=context.request_path,
        request_id=context.request_id,
    )


def snapshot(instance: models.Model, fields: Iterable[str]) -> dict[str, Any]:
    """
    Los valores de `fields` en `instance`, convertidos a valores de JSON.

    Una clave foránea se guarda como su `pk`, las fechas en ISO 8601 y los
    `Decimal` como texto.
    """
    values = {}
    for name in fields:
        field = instance._meta.get_field(name)
        values[name] = _to_json(field.value_from_object(instance))
    return values


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]:
    """
    `{campo: [antes, después]}` solo con los campos que cambiaron.

    Un campo que no está en `before` cuenta como `None`, así que al crear
    `antes` es `null`. Los campos de `SENSITIVE_FIELDS` quedan como
    `"[oculto]"`. Si nada cambió, devuelve `{}`.
    """
    changes: dict[str, list[Any]] = {}
    for name in [*before, *(key for key in after if key not in before)]:
        old, new = before.get(name), after.get(name)
        if old == new:
            continue
        changes[name] = [HIDDEN, HIDDEN] if name in SENSITIVE_FIELDS else [old, new]
    return changes


def _resolve_action(action: AuditAction | str) -> tuple[AuditAction, str]:
    try:
        action = AuditAction(action)
        return action, ACTION_CATEGORIES[action]
    except ValueError, KeyError:
        raise ValueError(
            f"La acción {action!r} no está en el catálogo de auditoría."
        ) from None


def _hide_sensitive(values: dict[str, Any]) -> dict[str, Any]:
    """
    Oculta los campos sensibles y deja los valores como JSON.

    `diff` ya los oculta; esto evita que un valor secreto llegue al registro si
    alguien pasa `changes` o `extra` armados a mano.
    """
    hidden = {}
    for name, value in values.items():
        if name in SENSITIVE_FIELDS:
            value = [HIDDEN, HIDDEN] if isinstance(value, list) else HIDDEN
        hidden[name] = _to_json(value)
    return hidden


def _to_json(value: Any) -> Any:
    """Convierte `value` a tipos nativos de JSON, como quedarán guardados."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
