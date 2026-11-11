"""Pruebas del trigger de inmutabilidad en PostgreSQL (SPEC 05, §3.3)."""

import pytest
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction

from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.models import AuditEvent, AuditSource

TRIGGER = "auditoria_auditevent_immutable"
MESSAGE = "auditoria_auditevent es inmutable"


def make_event() -> AuditEvent:
    return AuditEvent.objects.create(
        category=AuditCategory.ACCESS,
        action=AuditAction.LOGOUT,
        source=AuditSource.SYSTEM,
        actor_username="cobrador",
    )


def trigger_exists() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_trigger WHERE tgname = %s AND NOT tgisinternal",
            [TRIGGER],
        )
        return cursor.fetchone() is not None


@pytest.mark.django_db
def test_trigger_exists():
    assert trigger_exists()


@pytest.mark.django_db
def test_direct_sql_update_fails():
    event = make_event()

    with pytest.raises(DatabaseError, match=MESSAGE):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE auditoria_auditevent SET actor_username = 'otro' "
                "WHERE id = %s",
                [event.pk],
            )

    assert AuditEvent.objects.get(pk=event.pk).actor_username == "cobrador"


@pytest.mark.django_db
def test_direct_sql_delete_fails():
    event = make_event()

    with pytest.raises(DatabaseError, match=MESSAGE):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM auditoria_auditevent WHERE id = %s", [event.pk])

    assert AuditEvent.objects.filter(pk=event.pk).exists()


@pytest.mark.django_db
def test_insert_is_allowed():
    make_event()

    assert AuditEvent.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_migration_can_be_reverted_and_applied_again():
    try:
        call_command("migrate", "auditoria", "0001", verbosity=0)
        assert not trigger_exists()

        # Sin el trigger, el SQL directo sí modifica la tabla.
        event = make_event()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE auditoria_auditevent SET actor_username = 'otro' "
                "WHERE id = %s",
                [event.pk],
            )
    finally:
        call_command("migrate", "auditoria", verbosity=0)

    assert trigger_exists()
