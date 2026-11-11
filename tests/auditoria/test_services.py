"""Pruebas de record, snapshot y diff (SPEC 05, §3.6)."""

import uuid
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.models import User
from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.context import audit_context
from apps.auditoria.middleware import AuditContextMiddleware
from apps.auditoria.models import AuditEvent, AuditSource
from apps.auditoria.services import HIDDEN, diff, record, snapshot

pytestmark = pytest.mark.django_db


# record


def test_record_takes_the_category_from_the_catalog(user):
    event = record(AuditAction.USER_UPDATED, actor=user)

    assert event.category == AuditCategory.SECURITY
    assert record(AuditAction.LOGOUT, actor=user).category == AuditCategory.ACCESS


def test_record_accepts_the_action_value_as_text(user):
    event = record("auth.logout", actor=user)

    assert event.action == AuditAction.LOGOUT


@pytest.mark.parametrize("action", ["auth.no_existe", "", "AUTH.LOGOUT"])
def test_record_with_unknown_action_raises(action):
    with pytest.raises(ValueError, match="catálogo"):
        record(action)

    assert not AuditEvent.objects.exists()


def test_record_with_action_without_category_raises(monkeypatch):
    from apps.auditoria import services

    monkeypatch.setattr(services, "ACTION_CATEGORIES", {})

    with pytest.raises(ValueError, match="catálogo"):
        record(AuditAction.LOGOUT)


def test_record_saves_actor_and_target(make_user):
    actor = make_user("admin1")
    target = make_user("cobrador1", first_name="Ana")

    event = AuditEvent.objects.get(
        pk=record(AuditAction.USER_UPDATED, actor=actor, target=target).pk
    )

    assert event.actor == actor
    assert event.actor_username == "admin1"
    assert event.content_type == ContentType.objects.get_for_model(User)
    assert event.object_id == str(target.pk)
    assert event.object_repr == "cobrador1"


def test_record_without_actor_or_target():
    event = record(AuditAction.LOGIN_FAILED, identifier="desconocido")

    assert event.actor is None
    assert event.actor_username == ""
    assert event.content_type is None
    assert event.object_id == ""
    assert event.object_repr == ""
    assert event.identifier == "desconocido"


def test_record_truncates_identifier_and_object_repr(make_user):
    target = make_user("x" * 150)
    target.username = "y" * 250  # str(target) más largo que la columna

    event = record(AuditAction.LOGIN_FAILED, target=target, identifier="z" * 300)

    assert event.identifier == "z" * 150
    assert event.object_repr == "y" * 200


def test_record_keeps_actor_username_when_the_user_changes_later(make_user):
    actor = make_user("antes")
    event = record(AuditAction.LOGOUT, actor=actor)

    actor.username = "despues"
    actor.save()

    assert AuditEvent.objects.get(pk=event.pk).actor_username == "antes"


def test_record_saves_changes_and_extra_as_json(user):
    event = record(
        AuditAction.USER_DEACTIVATED,
        actor=user,
        changes={"is_active": (True, False)},
        extra={"reason": "Retiro", "monto": Decimal("1.50"), "id": uuid.UUID(int=1)},
    )
    stored = AuditEvent.objects.get(pk=event.pk)

    assert stored.changes == {"is_active": [True, False]}
    assert stored.extra == {
        "reason": "Retiro",
        "monto": "1.50",
        "id": "00000000-0000-0000-0000-000000000001",
    }
    # Lo que devuelve record es igual a lo guardado.
    assert event.changes == stored.changes
    assert event.extra == stored.extra


def test_record_hides_sensitive_values_passed_by_hand(user):
    event = record(
        AuditAction.USER_PASSWORD_RESET,
        actor=user,
        changes={"password": ["md5$a$hash1", "md5$b$hash2"]},
        extra={"password": "Temporal123"},
    )
    stored = AuditEvent.objects.get(pk=event.pk)

    assert stored.changes == {"password": [HIDDEN, HIDDEN]}
    assert stored.extra == {"password": HIDDEN}


def test_record_writes_in_the_callers_transaction(user):
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            record(AuditAction.LOGOUT, actor=user)
            raise RuntimeError

    assert not AuditEvent.objects.exists()


# Contexto


def test_outside_a_request_the_source_is_system():
    event = record(AuditAction.LOGOUT)

    assert event.source == AuditSource.SYSTEM
    assert event.ip_address is None
    assert event.request_id is None
    assert event.user_agent == ""
    assert event.request_method == ""
    assert event.request_path == ""


def test_inside_audit_context_the_source_is_command():
    with audit_context(source=AuditSource.COMMAND):
        event = record(AuditAction.LOGOUT)

    assert event.source == AuditSource.COMMAND


def run_request(path: str, view, **meta) -> None:
    AuditContextMiddleware(view)(RequestFactory().post(path, **meta))


def test_records_of_one_request_share_the_request_context():
    def view(request):
        record(AuditAction.LOGIN_FAILED, identifier="a")
        record(AuditAction.ACCOUNT_LOCKED)
        return HttpResponse()

    run_request(
        "/ingresar/?next=/usuarios/",
        view,
        REMOTE_ADDR="10.0.0.1",
        HTTP_USER_AGENT="Navegador/1.0",
    )

    first, second = AuditEvent.objects.order_by("id")
    assert first.request_id is not None
    assert first.request_id == second.request_id
    assert first.source == AuditSource.WEB
    assert first.ip_address == "10.0.0.1"
    assert first.user_agent == "Navegador/1.0"
    assert first.request_method == "POST"
    assert first.request_path == "/ingresar/"


def test_two_requests_have_different_request_ids():
    def view(request):
        record(AuditAction.LOGOUT)
        return HttpResponse()

    run_request("/", view)
    run_request("/", view)

    first, second = AuditEvent.objects.order_by("id")
    assert first.request_id != second.request_id


@pytest.mark.parametrize(
    ("path", "source"),
    [("/admin/accounts/user/1/change/", AuditSource.ADMIN), ("/usuarios/", "web")],
)
def test_source_depends_on_the_path(path, source):
    def view(request):
        record(AuditAction.USER_UPDATED)
        return HttpResponse()

    run_request(path, view)

    assert AuditEvent.objects.get().source == source


# snapshot


def test_snapshot_returns_the_requested_fields(make_user):
    user = make_user("ana", first_name="Ana", email="ana@example.com")

    assert snapshot(user, ["first_name", "email", "is_active"]) == {
        "first_name": "Ana",
        "email": "ana@example.com",
        "is_active": True,
    }


def test_snapshot_converts_foreign_keys_and_datetimes(make_user):
    actor = make_user("admin1")
    event = record(AuditAction.LOGOUT, actor=actor)

    values = snapshot(event, ["actor", "occurred_at", "request_id"])

    assert values["actor"] == actor.pk
    assert isinstance(values["occurred_at"], str)
    assert values["occurred_at"].startswith(event.occurred_at.date().isoformat())
    assert values["request_id"] is None


def test_snapshot_of_unknown_field_raises(user):
    from django.core.exceptions import FieldDoesNotExist

    with pytest.raises(FieldDoesNotExist):
        snapshot(user, ["no_existe"])


# diff


def test_diff_returns_only_changed_fields():
    before = {"first_name": "Ana", "email": "a@example.com", "is_active": True}
    after = {"first_name": "Ana María", "email": "a@example.com", "is_active": True}

    assert diff(before, after) == {"first_name": ["Ana", "Ana María"]}


def test_diff_without_changes_is_empty():
    values = {"first_name": "Ana", "role": "Supervisor"}

    assert diff(values, dict(values)) == {}


def test_diff_from_nothing_has_null_before():
    assert diff({}, {"first_name": "Ana", "role": "Supervisor"}) == {
        "first_name": [None, "Ana"],
        "role": [None, "Supervisor"],
    }


def test_diff_hides_sensitive_fields():
    changes = diff(
        {"password": "md5$a$hash1", "email": ""},
        {"password": "md5$b$hash2", "email": ""},
    )

    assert changes == {"password": [HIDDEN, HIDDEN]}
    assert HIDDEN == "[oculto]"


def test_diff_ignores_unchanged_sensitive_fields():
    assert diff({"password": "md5$a$hash"}, {"password": "md5$a$hash"}) == {}


def test_diff_includes_fields_removed_in_after():
    assert diff({"phone": "3001234567"}, {}) == {"phone": ["3001234567", None]}
