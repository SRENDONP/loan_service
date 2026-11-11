"""
Registro de auditoría inmutable (SPEC 05, §3.2 y §3.3).

La única forma de escribir es crear un registro nuevo, y eso lo hace
`apps.auditoria.services.record`. La aplicación rechaza la edición y el
borrado, y en PostgreSQL un trigger cierra cualquier otro camino.
"""

from typing import Any, NoReturn

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.exceptions import ImmutableAuditEventError


class AuditSource(models.TextChoices):
    WEB = "web", _("Aplicación web")
    ADMIN = "admin", _("Admin de Django")
    COMMAND = "command", _("Comando de gestión")
    SYSTEM = "system", _("Sistema")


class AuditEventQuerySet(models.QuerySet):
    """QuerySet que rechaza las escrituras masivas sobre registros existentes."""

    def update(self, **kwargs: Any) -> NoReturn:
        raise ImmutableAuditEventError()

    def delete(self) -> NoReturn:
        raise ImmutableAuditEventError()

    def bulk_update(self, objs: Any, fields: Any, batch_size: Any = None) -> NoReturn:
        raise ImmutableAuditEventError()


class AuditEvent(models.Model):
    occurred_at = models.DateTimeField(
        _("fecha y hora"), default=timezone.now, db_index=True
    )
    category = models.CharField(
        _("categoría"), max_length=20, choices=AuditCategory.choices, db_index=True
    )
    action = models.CharField(
        _("acción"), max_length=64, choices=AuditAction.choices, db_index=True
    )
    source = models.CharField(_("origen"), max_length=10, choices=AuditSource.choices)

    # Quién
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("usuario"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor_username = models.CharField(
        _("nombre de usuario"), max_length=150, blank=True
    )
    identifier = models.CharField(
        _("identificador escrito"), max_length=150, blank=True
    )

    # Sobre qué
    content_type = models.ForeignKey(
        ContentType,
        verbose_name=_("tipo de entidad"),
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    object_id = models.CharField(_("id de la entidad"), max_length=64, blank=True)
    object_repr = models.CharField(_("entidad"), max_length=200, blank=True)

    # Qué cambió
    changes = models.JSONField(
        _("cambios"), default=dict, blank=True, encoder=DjangoJSONEncoder
    )
    extra = models.JSONField(
        _("contexto adicional"), default=dict, blank=True, encoder=DjangoJSONEncoder
    )

    # Desde dónde
    ip_address = models.GenericIPAddressField(_("dirección IP"), null=True, blank=True)
    user_agent = models.CharField(_("navegador"), max_length=255, blank=True)
    request_method = models.CharField(_("método HTTP"), max_length=10, blank=True)
    request_path = models.CharField(_("ruta"), max_length=255, blank=True)
    request_id = models.UUIDField(
        _("id de la petición"), null=True, blank=True, db_index=True
    )

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de auditoría")
        verbose_name_plural = _("registros de auditoría")
        ordering = ["-occurred_at", "-id"]
        # Los registros solo se consultan: no hay permisos de agregar, editar ni
        # borrar (SPEC 05, §3.3).
        default_permissions = ("view",)
        indexes = [
            models.Index(
                fields=["content_type", "object_id"], name="auditoria_entity_idx"
            ),
            models.Index(fields=["actor", "occurred_at"], name="auditoria_actor_idx"),
        ]

    def __str__(self) -> str:
        when = timezone.localtime(self.occurred_at)
        return f"{self.get_action_display()} ({when:%Y-%m-%d %H:%M:%S})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ImmutableAuditEventError()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise ImmutableAuditEventError()
