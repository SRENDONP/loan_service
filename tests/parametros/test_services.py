"""Pruebas del servicio de parámetros globales (SPEC 06, §3.3)."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.parametros.models import GlobalSettings, RoundingMode, Weekday
from apps.parametros.services import (
    RoundingRule,
    get_rounding_rule,
    get_settings,
    is_business_day,
    update_business,
    update_collection,
    update_rounding,
    update_security,
)

pytestmark = pytest.mark.django_db

# Una semana sin festivos. (El lunes 16 de noviembre de 2026 es festivo desde
# la SPEC 07: Independencia de Cartagena.)
SUNDAY = date(2026, 11, 22)
MONDAY = date(2026, 11, 23)
SATURDAY = date(2026, 11, 21)


# Lectura


def test_get_settings_returns_the_row():
    settings = get_settings()

    assert settings.pk == 1
    assert GlobalSettings.objects.count() == 1


def test_get_settings_recreates_the_row_with_defaults():
    # Como después de un flush en una prueba transaccional.
    GlobalSettings.objects.all().delete()

    settings = get_settings()

    assert settings.pk == 1
    assert settings.business_name == "Gestión de préstamos"
    assert settings.max_failed_attempts == 5
    assert GlobalSettings.objects.count() == 1


def test_get_settings_reads_the_current_value_without_cache():
    get_settings()
    GlobalSettings.objects.filter(pk=1).update(business_name="Créditos Ya")

    assert get_settings().business_name == "Créditos Ya"


def test_fixture_changes_are_visible_to_the_service(global_settings):
    global_settings.business_name = "Créditos Ya"
    global_settings.save()

    assert get_settings().business_name == "Créditos Ya"


# Redondeo


def test_default_rounding_rule():
    assert get_rounding_rule() == RoundingRule(
        multiple=Decimal("50"), mode=RoundingMode.HALF_UP
    )


def test_rounding_rule_follows_the_row(global_settings):
    global_settings.rounding_multiple = 1000
    global_settings.rounding_mode = RoundingMode.UP
    global_settings.save()

    rule = get_rounding_rule()

    assert rule.multiple == Decimal("1000")
    assert isinstance(rule.multiple, Decimal)
    assert rule.mode is RoundingMode.UP


# Días hábiles


def test_sunday_is_not_a_business_day_by_default():
    assert is_business_day(SUNDAY) is False


def test_monday_and_saturday_are_business_days_by_default():
    assert is_business_day(MONDAY) is True
    assert is_business_day(SATURDAY) is True


def test_business_days_follow_the_row(global_settings):
    global_settings.non_business_weekdays = [Weekday.SATURDAY, Weekday.SUNDAY]
    global_settings.save()

    assert is_business_day(SATURDAY) is False
    assert is_business_day(SUNDAY) is False
    assert is_business_day(MONDAY) is True


def test_every_day_is_a_business_day_without_non_business_weekdays(global_settings):
    global_settings.non_business_weekdays = []
    global_settings.save()

    assert is_business_day(SUNDAY) is True


# Edición


@pytest.fixture
def editor(make_user):
    """Usuario con permiso de editar los parámetros (el rol llega en el paso 7)."""
    from django.contrib.auth.models import Permission

    user = make_user("editor")
    user.user_permissions.add(Permission.objects.get(codename="change_globalsettings"))
    return user


UPDATES = [
    (update_business, {"business_name": "Créditos Ya"}, "business_name", "Créditos Ya"),
    (
        update_collection,
        {"collection_weekdays": [1, 2, 3]},
        "collection_weekdays",
        [1, 2, 3],
    ),
    (update_rounding, {"rounding_multiple": 100}, "rounding_multiple", 100),
    (update_security, {"max_failed_attempts": 7}, "max_failed_attempts", 7),
]


@pytest.mark.parametrize(("service", "data", "field", "value"), UPDATES)
def test_update_saves_the_group_field_and_editor(editor, service, data, field, value):
    result = service(editor, data)

    row = GlobalSettings.objects.get()
    assert getattr(row, field) == value
    assert getattr(result, field) == value
    assert row.updated_by == editor


@pytest.mark.parametrize(("service", "data", "field", "value"), UPDATES)
def test_update_without_permission_is_denied(make_user, service, data, field, value):
    with pytest.raises(PermissionDenied):
        service(make_user("sin_permiso"), data)

    assert getattr(GlobalSettings.objects.get(), field) != value


def test_update_ignores_fields_of_other_groups(editor):
    update_rounding(editor, {"rounding_multiple": 100, "business_name": "Otro"})

    row = GlobalSettings.objects.get()
    assert row.rounding_multiple == 100
    assert row.business_name == "Gestión de préstamos"


def test_update_keeps_group_fields_not_in_data(editor):
    update_security(editor, {"lockout_minutes": 30})

    row = GlobalSettings.objects.get()
    assert row.lockout_minutes == 30
    assert row.max_failed_attempts == 5


def test_update_normalizes_before_saving(editor):
    update_business(editor, {"currency_code": "usd", "business_name": "  Ya  "})

    row = GlobalSettings.objects.get()
    assert row.currency_code == "USD"
    assert row.business_name == "Ya"


def test_invalid_update_raises_field_errors_and_does_not_change_the_row(editor):
    with pytest.raises(ValidationError) as excinfo:
        update_security(editor, {"max_failed_attempts": 2, "lockout_minutes": 30})

    assert "max_failed_attempts" in excinfo.value.message_dict
    row = GlobalSettings.objects.get()
    assert row.max_failed_attempts == 5
    assert row.lockout_minutes == 15


def test_cross_field_rule_is_checked(editor):
    with pytest.raises(ValidationError) as excinfo:
        update_security(
            editor, {"session_idle_timeout_minutes": 60, "session_max_hours": 1}
        )

    assert "session_idle_timeout_minutes" in excinfo.value.message_dict


def test_update_without_changes_does_not_save(editor):
    before = GlobalSettings.objects.get().updated_at

    update_rounding(editor, {"rounding_multiple": 50, "rounding_mode": "half_up"})

    row = GlobalSettings.objects.get()
    assert row.updated_at == before
    assert row.updated_by is None


def test_update_recreates_a_missing_row(editor):
    GlobalSettings.objects.all().delete()

    update_rounding(editor, {"rounding_multiple": 10})

    assert GlobalSettings.objects.get().rounding_multiple == 10


def test_no_module_outside_parametros_uses_the_model_directly():
    # ADR-001 y SPEC 06, §3.3: el resto del sistema lee por el servicio.
    apps_dir = Path(__file__).resolve().parents[2] / "apps"
    offenders = [
        str(module.relative_to(apps_dir))
        for module in apps_dir.rglob("*.py")
        if "parametros" not in module.relative_to(apps_dir).parts
        and "GlobalSettings" in module.read_text(encoding="utf-8")
    ]

    assert offenders == []
