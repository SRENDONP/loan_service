"""
Registro de auditoría en el admin de Django, de solo lectura (SPEC 05, §3.8).

Mientras llega la pantalla de consulta (SPEC 25), los superusuarios revisan
aquí los registros. El sitio del admin ya exige superusuario (SPEC 03).
"""

import json
from typing import Any

from django.contrib import admin
from django.contrib.admin import ActionLocation
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.auditoria.models import AuditEvent

FIELDS = (
    "occurred_at",
    "category",
    "action",
    "source",
    "actor",
    "actor_username",
    "identifier",
    "content_type",
    "object_id",
    "object_repr",
    "changes_display",
    "extra_display",
    "ip_address",
    "user_agent",
    "request_method",
    "request_path",
    "request_id",
)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "occurred_at",
        "category",
        "action",
        "actor_username",
        "object_repr",
        "ip_address",
        "source",
    )
    list_filter = ("category", "action", "source", "occurred_at")
    search_fields = (
        "actor_username",
        "identifier",
        "object_repr",
        "ip_address",
        "request_id",
    )
    date_hierarchy = "occurred_at"
    list_select_related = ("actor", "content_type")
    fields = FIELDS
    readonly_fields = FIELDS

    @admin.display(description=_("cambios"))
    def changes_display(self, obj: AuditEvent) -> str:
        return _pretty_json(obj.changes)

    @admin.display(description=_("contexto adicional"))
    def extra_display(self, obj: AuditEvent) -> str:
        return _pretty_json(obj.extra)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: AuditEvent | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: AuditEvent | None = None
    ) -> bool:
        return False

    def get_actions(
        self,
        request: HttpRequest,
        action_location: ActionLocation = ActionLocation.CHANGE_LIST,
    ) -> dict[str, Any]:
        actions = super().get_actions(request, action_location=action_location)
        actions.pop("delete_selected", None)
        return actions


def _pretty_json(value: Any) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    return format_html("<pre>{}</pre>", text)
