"""Pruebas de la auditoría de los parámetros globales (SPEC 06, §3.7)."""

from datetime import time

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.models import AuditEvent
from apps.parametros import services
from apps.parametros.models import GlobalSettings, Weekday
from apps.parametros.services import (
    update_business,
    update_collection,
    update_rounding,
    update_security,
)

pytestmark = pytest.mark.django_db

SETTINGS_ACTIONS = [
    AuditAction.SETTINGS_BUSINESS_UPDATED,
    AuditAction.SETTINGS_COLLECTION_UPDATED,
    AuditAction.SETTINGS_ROUNDING_UPDATED,
    AuditAction.SETTINGS_SECURITY_UPDATED,
]


@pytest.fixture
def editor(make_user):
    user = make_user("editor")
    user.user_permissions.add(Permission.objects.get(codename="change_globalsettings"))
    return user


def settings_events():
    return AuditEvent.objects.filter(action__in=SETTINGS_ACTIONS)


@pytest.mark.parametrize(
    ("service", "data", "action", "category", "changes"),
    [
        (
            update_business,
            {"business_name": "Créditos Ya", "brand_icon": "fas fa-coins"},
            AuditAction.SETTINGS_BUSINESS_UPDATED,
            AuditCategory.SECURITY,
            {
                "business_name": ["Gestión de préstamos", "Créditos Ya"],
                "brand_icon": ["fas fa-hand-holding-usd", "fas fa-coins"],
            },
        ),
        (
            update_collection,
            {"holiday_shift_rule": "affected_only"},
            AuditAction.SETTINGS_COLLECTION_UPDATED,
            AuditCategory.FINANCIAL,
            {"holiday_shift_rule": ["cascade", "affected_only"]},
        ),
        (
            update_rounding,
            {"rounding_multiple": 100, "rounding_mode": "up"},
            AuditAction.SETTINGS_ROUNDING_UPDATED,
            AuditCategory.FINANCIAL,
            {"rounding_multiple": [50, 100], "rounding_mode": ["half_up", "up"]},
        ),
        (
            update_security,
            {"max_failed_attempts": 3, "lockout_minutes": 15},
            AuditAction.SETTINGS_SECURITY_UPDATED,
            AuditCategory.SECURITY,
            {"max_failed_attempts": [5, 3]},
        ),
    ],
)
def test_each_update_records_its_action(
    editor, service, data, action, category, changes
):
    service(editor, data)

    [event] = settings_events()
    assert event.action == action
    assert event.category == category
    assert event.actor == editor
    assert event.content_type == ContentType.objects.get_for_model(GlobalSettings)
    assert event.object_id == "1"
    # Solo los campos del grupo que cambiaron.
    assert event.changes == changes


def test_collection_days_and_hours_are_stored_as_json(editor):
    update_collection(
        editor,
        {
            "collection_weekdays": [Weekday.MONDAY, Weekday.FRIDAY],
            "collection_start_time": time(7, 30),
        },
    )

    [event] = settings_events()
    assert event.changes == {
        "collection_weekdays": [[1, 2, 3, 4, 5, 6], [1, 5]],
        "collection_start_time": ["06:00:00", "07:30:00"],
    }


def test_update_without_changes_records_nothing(editor):
    update_security(editor, {"max_failed_attempts": 5})

    assert not settings_events().exists()


def test_failed_record_rolls_back_the_update(editor, monkeypatch):
    def broken_record(*args, **kwargs):
        raise RuntimeError("falla la auditoría")

    monkeypatch.setattr(services, "record", broken_record)

    with pytest.raises(RuntimeError):
        update_business(editor, {"business_name": "Créditos Ya"})

    row = GlobalSettings.objects.get()
    assert row.business_name == "Gestión de préstamos"
    assert row.updated_by is None


def test_update_without_permission_records_nothing(make_user):
    with pytest.raises(PermissionDenied):
        update_rounding(make_user("sin_permiso"), {"rounding_multiple": 100})

    assert not settings_events().exists()


def test_invalid_update_records_nothing(editor):
    with pytest.raises(ValidationError):
        update_security(editor, {"max_failed_attempts": 99})

    assert not settings_events().exists()
