"""Pruebas del modelo y de su inmutabilidad en la aplicación (SPEC 05, §3.2 y §3.3)."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import connection

from apps.accounts import roles
from apps.accounts.roles import ROLE_PERMISSIONS, USER_MANAGEMENT_PERMISSIONS
from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.exceptions import ImmutableAuditEventError
from apps.auditoria.models import AuditEvent, AuditSource

pytestmark = pytest.mark.django_db


@pytest.fixture
def event() -> AuditEvent:
    return AuditEvent.objects.create(
        category=AuditCategory.ACCESS,
        action=AuditAction.LOGIN_SUCCEEDED,
        source=AuditSource.WEB,
        actor_username="cobrador",
    )


def test_table_has_the_spec_indexes():
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(
            cursor, AuditEvent._meta.db_table
        )

    assert AuditEvent._meta.db_table == "auditoria_auditevent"
    assert constraints["auditoria_entity_idx"]["columns"] == [
        "content_type_id",
        "object_id",
    ]
    assert constraints["auditoria_actor_idx"]["columns"] == [
        "actor_id",
        "occurred_at",
    ]


def test_new_event_can_be_saved(event):
    assert AuditEvent.objects.filter(pk=event.pk).exists()
    assert event.changes == {}
    assert event.extra == {}
    assert event.occurred_at is not None


def test_str_shows_action_and_date(event):
    assert str(event).startswith("Ingreso exitoso (")


def test_str_uses_local_time():
    from datetime import UTC, datetime

    event = AuditEvent(
        action=AuditAction.LOGOUT,
        occurred_at=datetime(2026, 11, 11, 20, 54, 19, tzinfo=UTC),
    )

    # America/Bogota es UTC-5.
    assert str(event) == "Cierre de sesión (2026-11-11 15:54:19)"


def test_immutable_error_is_permission_denied():
    assert issubclass(ImmutableAuditEventError, PermissionDenied)


def test_saving_an_existing_event_raises(event):
    event.actor_username = "otro"

    with pytest.raises(ImmutableAuditEventError):
        event.save()

    assert AuditEvent.objects.get(pk=event.pk).actor_username == "cobrador"


def test_saving_a_fetched_event_raises(event):
    fetched = AuditEvent.objects.get(pk=event.pk)

    with pytest.raises(ImmutableAuditEventError):
        fetched.save()


def test_deleting_an_event_raises(event):
    with pytest.raises(ImmutableAuditEventError):
        event.delete()

    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_queryset_update_raises(event):
    with pytest.raises(ImmutableAuditEventError):
        AuditEvent.objects.filter(pk=event.pk).update(actor_username="otro")

    assert AuditEvent.objects.get(pk=event.pk).actor_username == "cobrador"


def test_queryset_delete_raises(event):
    with pytest.raises(ImmutableAuditEventError):
        AuditEvent.objects.filter(pk=event.pk).delete()

    with pytest.raises(ImmutableAuditEventError):
        AuditEvent.objects.all().delete()

    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_bulk_update_raises(event):
    event.actor_username = "otro"

    with pytest.raises(ImmutableAuditEventError):
        AuditEvent.objects.bulk_update([event], ["actor_username"])

    assert AuditEvent.objects.get(pk=event.pk).actor_username == "cobrador"


def test_only_view_permission_exists():
    codenames = set(
        Permission.objects.filter(content_type__app_label="auditoria").values_list(
            "codename", flat=True
        )
    )

    assert codenames == {"view_auditevent"}


def test_no_role_has_auditoria_permissions():
    for perms in ROLE_PERMISSIONS.values():
        assert not any(perm.startswith("auditoria.") for perm in perms)

    assert not Group.objects.filter(
        permissions__content_type__app_label="auditoria"
    ).exists()


def test_auditoria_is_the_last_app_with_models():
    # El receptor de sync_roles (ADR-002) corre con la señal de la última app
    # con modelos, que ahora es auditoria.
    assert roles._last_app_with_models().label == "auditoria"


def test_migrate_still_syncs_the_four_roles():
    # La base de pruebas se crea con migrate sobre una base vacía.
    administrator = Group.objects.get(name="Administrador")
    perms = {
        f"{app}.{codename}"
        for app, codename in administrator.permissions.values_list(
            "content_type__app_label", "codename"
        )
    }

    assert perms == USER_MANAGEMENT_PERMISSIONS
    for name in ("Supervisor", "Cajero/Cobrador", "Consulta"):
        assert not Group.objects.get(name=name).permissions.exists()
